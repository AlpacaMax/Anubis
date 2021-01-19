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
from anubis.utils.redis_queue import enqueue_webhook

webhook = Blueprint("public-webhook", __name__, url_prefix="/public/webhook")


def webhook_log_msg():
    if (
        request.headers.get("Content-Type", None) == "application/json"
        and request.headers.get("X-GitHub-Event", None) == "push"
    ):
        return request.json["pusher"]["name"]
    return None


@webhook.route("/", methods=["POST"])
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

    webhook = request.json

    # Load the basics from the webhook
    repo_url = webhook["repository"]["url"]
    github_username = webhook["pusher"]["name"]
    commit = webhook["after"]
    assignment_name = webhook["repository"]["name"][: -(len(github_username) + 1)]

    # Attempt to find records for the relevant models
    assignment = Assignment.query.filter(
        Assignment.unique_code.in_(webhook["repository"]["name"].split("-"))
    ).first()

    # Get github username from the repository name
    repo_name_split = webhook["repository"]["name"].split("-")
    unique_code_index = repo_name_split.index(assignment.unique_code)
    repo_name_split = repo_name_split[unique_code_index + 1 :]
    github_username1 = "-".join(repo_name_split)
    github_username2 = "-".join(repo_name_split[:-1])
    user = User.query.filter(
        User.github_username.in_([github_username1, github_username2])
    ).first()

    # The before Hash will be all 0s on for the first hash.
    # We will want to ignore both this first push (the initialization of the repo)
    # and all branches that are not master.
    if webhook["before"] == "0000000000000000000000000000000000000000":
        # Record that a new repo was created (and therefore, someone just
        # started their assignment)
        logger.info(
            "new student repo ",
            extra={
                "repo_url": repo_url,
                "github_username": github_username,
                "assignment_name": assignment_name,
                "commit": commit,
            },
        )

        if user is not None:
            repo = AssignmentRepo(
                owner=user,
                assignment=assignment,
                repo_url=repo_url,
                github_username=user.github_username,
            )
            db.session.add(repo)
            db.session.commit()

        esindex("new-repo", repo_url=repo_url, assignment=str(assignment))
        return success_response("initial commit")

    # Verify that we can match this push to an assignment
    if assignment is None:
        logger.error(
            "Could not find assignment",
            extra={
                "repo_url": repo_url,
                "github_username": github_username,
                "assignment_name": assignment_name,
                "commit": commit,
            },
        )
        return error_response("assignment not found"), 406

    repo = (
        AssignmentRepo.query.join(Assignment)
        .join(Course)
        .join(InCourse)
        .join(User)
        .filter(
            User.github_username == github_username,
            Assignment.unique_code == assignment.unique_code,
            AssignmentRepo.repo_url == repo_url,
        )
        .first()
    )

    logger.debug(
        "webhook data",
        extra={
            "github_username": github_username,
            "assignment": assignment.name,
            "repo_url": repo_url,
            "commit": commit,
            "unique_code": assignment.unique_code,
        },
    )

    if not is_debug():
        # Make sure that the repo we're about to process actually belongs to
        # our organization
        if not webhook["repository"]["full_name"].startswith("os3224/"):
            logger.error(
                "Invalid github organization in webhook.",
                extra={
                    "repo_url": repo_url,
                    "github_username": github_username,
                    "assignment_name": assignment_name,
                    "commit": commit,
                },
            )
            return error_response("invalid repo"), 406

    # if we dont have a record of the repo, then add it
    if repo is None:
        repo = AssignmentRepo(
            owner=user,
            assignment=assignment,
            repo_url=repo_url,
            github_username=github_username,
        )
        db.session.add(repo)
        db.session.commit()

    if webhook["ref"] != "refs/heads/master":
        logger.warning(
            "not push to master",
            extra={
                "repo_url": repo_url,
                "github_username": github_username,
                "assignment_name": assignment_name,
                "commit": commit,
            },
        )
        return error_response("not push to master")

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

    # Create the related submission models
    submission.init_submission_models()

    # If a user has not given us their github username
    # the submission will stay in a "dangling" state
    if user is None:
        logger.warning(
            "dangling submission from {}".format(github_username),
            extra={
                "repo_url": repo_url,
                "github_username": github_username,
                "assignment_name": assignment_name,
                "commit": commit,
            },
        )
        esindex(
            type="error",
            logs="dangling submission by: " + github_username,
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