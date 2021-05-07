from flask import Blueprint, request

from anubis.models import User, Submission
from anubis.utils.auth import current_user, require_user
from anubis.utils.http.decorators import json_response
from anubis.utils.http.https import error_response, success_response
from anubis.utils.lms.submissions import regrade_submission, get_submissions
from anubis.utils.services.elastic import log_endpoint
from anubis.utils.services.logger import logger

submissions = Blueprint(
    "public-submissions", __name__, url_prefix="/public/submissions"
)


@submissions.route("/")
@require_user()
@log_endpoint("public-submissions")
@json_response
def public_submissions():
    """
    Get all submissions for a given student. Optionally specify class,
    and assignment name filters in get query.


    /api/public/submissions
    /api/public/submissions?class=Intro to OS
    /api/public/submissions?assignment=Assignment 1: uniq
    /api/public/submissions?class=Intro to OS&assignment=Assignment 1: uniq

    :return:
    """
    # Get optional filters
    course_id = request.args.get("courseId", default=None)
    perspective_of_id = request.args.get("userId", default=None)
    assignment_id = request.args.get("assignmentId", default=None)

    # Load current user
    user: User = current_user()

    if perspective_of_id is not None and not (user.is_superuser):
        return error_response("Bad Request"), 400

    logger.debug("id: " + str(perspective_of_id))
    logger.debug("id: " + str(perspective_of_id or user.id))

    submissions_ = get_submissions(
        user_id=perspective_of_id or user.id,
        course_id=course_id,
        assignment_id=assignment_id,
    )

    if submissions_ is None:
        return error_response("Bad Request"), 400

    # Get submissions through cached function
    return success_response({"submissions": submissions_})


@submissions.route("/get/<string:commit>")
@require_user()
@log_endpoint(
    "public-submission-commit", lambda: "get submission {}".format(request.path)
)
@json_response
def public_submission(commit: str):
    """
    Get submission data for a given commit.

    :param commit:
    :return:
    """
    # Get current user
    user: User = current_user()

    if not user.is_superuser:
        # Try to find commit (verifying ownership)
        s = Submission.query.filter(
            Submission.owner_id == user.id,
            Submission.commit == commit,
        ).first()

    else:
        # Try to find commit (verifying not ownership)
        s = Submission.query.filter(
            Submission.commit == commit,
        ).first()

    # Make sure we caught one
    if s is None:
        return error_response("Submission does not exist")

    # Hand back submission
    return success_response({"submission": s.full_data})


@submissions.route("/regrade/<commit>")
@require_user()
@log_endpoint("regrade-request", lambda: "submission regrade request " + request.path)
@json_response
def public_regrade_commit(commit=None):
    """
    This route will get hit whenever someone clicks the regrade button on a
    processed assignment. It should do some validity checks on the commit and
    netid, then reset the submission and re-enqueue the submission job.
    """
    if commit is None:
        return error_response("incomplete_request"), 406

    # Load current user
    user: User = current_user()

    # Find the submission
    submission: Submission = (
        Submission.query.join(User)
            .filter(Submission.commit == commit, User.netid == user.netid)
            .first()
    )

    # Verify Ownership
    if submission is None:
        return error_response("invalid commit hash or netid"), 406

    # Check that autograde is enabled for the assignment
    if not submission.assignment.autograde_enabled:
        return error_response('Autograde is disabled for this assignment'), 400

    # Regrade
    return regrade_submission(submission)
