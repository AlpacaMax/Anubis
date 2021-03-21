from datetime import datetime, timedelta

from flask import Blueprint, request

from anubis.models import (
    Assignment,
    User,
    AssignmentRepo,
    db,
    Course,
    InCourse,
    Submission,
)
from anubis.utils.data import is_debug
from anubis.utils.decorators import json_response
from anubis.utils.elastic import log_endpoint, esindex
from anubis.utils.http import error_response, success_response
from anubis.utils.logger import logger
from anubis.utils.rpc import enqueue_webhook
from anubis.utils.webhook import parse_webhook, guess_github_username, check_repo

webhook = Blueprint("public-webhook", __name__, url_prefix="/public/webhook")


def webhook_log_msg():
    if (
            request.headers.get("Content-Type", None) == "application/json"
            and request.headers.get("X-GitHub-Event", None) == "push"
    ):
        return request.json["pusher"]["name"]
    return None


@webhook.route("/", methods=["POST"])
@webhook.route("/backup", methods=["POST"])
@log_endpoint("webhook", webhook_log_msg)
@json_response
def public_webhook():
    """
    This route should be hit by the github when a push happens.
    We should take the the github repo url and enqueue it as a job.
    """

    content_type = request.headers.get("Content-Type", None)
    x_github_event = request.headers.get("X-GitHub-Event", None)

    # Verify some expected headers
    if not (content_type == "application/json" and x_github_event == "push"):
        return error_response("Unable to verify webhook")

    # Load the basics from the webhook
    repo_url, repo_name, pusher_username, commit, before, ref = parse_webhook(request.json)

    # Attempt to find records for the relevant models
    assignment = Assignment.query.filter(
        Assignment.unique_code.in_(repo_name.split("-"))
    ).first()

    # Verify that we can match this push to an assignment
    if assignment is None:
        logger.error(
            "Could not find assignment",
            extra={
                "repo_url": repo_url,
                "pusher_username": pusher_username,
                "commit": commit,
            },
        )
        return error_response("assignment not found"), 406

    # Get github username from the repository name
    user, github_username_guess = guess_github_username(assignment, repo_name)

    # The before Hash will be all 0s on for the first hash.
    # We will want to ignore both this first push (the initialization of the repo)
    # and all branches that are not master.
    if before == "0000000000000000000000000000000000000000":
        # Record that a new repo was created (and therefore, someone just
        # started their assignment)
        logger.debug(
            "new student repo ",
            extra={
                "repo_url": repo_url,
                "github_username": github_username_guess,
                "pusher": pusher_username,
                "commit": commit,
            },
        )

        check_repo(assignment, repo_url, github_username_guess, user)

        esindex("new-repo", repo_url=repo_url, assignment=str(assignment))
        return success_response("initial commit")

    repo = (
        AssignmentRepo.query.join(Assignment)
            .join(Course)
            .join(InCourse)
            .join(User)
            .filter(
            User.github_username == github_username_guess,
            Assignment.unique_code == assignment.unique_code,
            AssignmentRepo.repo_url == repo_url,
        )
            .first()
    )

    logger.debug(
        "webhook data",
        extra={
            "assignment": assignment.name,
            "repo_url": repo_url,
            "commit": commit,
            "unique_code": assignment.unique_code,
        },
    )

    if not is_debug():
        # Make sure that the repo we're about to process actually belongs to
        # our organization
        if not request.json["repository"]["full_name"].startswith("os3224/"):
            logger.error(
                "Invalid github organization in webhook.",
                extra={
                    "repo_url": repo_url,
                    "pusher_username": pusher_username,
                    "commit": commit,
                },
            )
            return error_response("invalid repo"), 406

    # if we dont have a record of the repo, then add it
    if repo is None:
        repo = check_repo(assignment, repo_url, github_username_guess, user)

    if ref != "refs/heads/master":
        logger.warning(
            "not push to master",
            extra={
                "repo_url": repo_url,
                "github_username": github_username_guess,
                "commit": commit,
            },
        )
        return error_response("not push to master")

    submission = Submission.query.filter_by(commit=commit).first()
    if submission is None:
        # Create a shiny new submission
        submission = Submission(
            assignment=assignment,
            repo=repo,
            owner=user,
            commit=commit,
            state="Waiting for resources...",
        )
        db.session.add(submission)
        db.session.commit()
    elif submission.created < datetime.now() - timedelta(minutes=3):
        return success_response({'status': 'already created'})

    # Create the related submission models
    submission.init_submission_models()

    # If a user has not given us their github username
    # the submission will stay in a "dangling" state
    if user is None:
        logger.warning(
            "dangling submission from {}".format(github_username_guess),
            extra={
                "repo_url": repo_url,
                "github_username": github_username_guess,
                "commit": commit,
            },
        )
        esindex(
            type="error",
            logs="dangling submission by: " + github_username_guess,
            submission=submission.data,
            neitd=None,
        )
        return error_response("dangling submission")

    # Log the submission
    esindex(
        index="submission",
        processed=0,
        error=-1,
        passed=-1,
        netid=submission.netid,
        commit=submission.commit,
    )

    # if the github username is not found, create a dangling submission
    enqueue_webhook(submission.id)

    return success_response("submission accepted")
