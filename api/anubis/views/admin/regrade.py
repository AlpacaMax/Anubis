from datetime import datetime, timedelta

from flask import Blueprint

from anubis.models import Submission, Assignment, User, Course, InCourse
from anubis.rpc.batch import rpc_bulk_regrade
from anubis.utils.auth import require_admin
from anubis.utils.data import split_chunks
from anubis.utils.decorators import json_response
from anubis.utils.elastic import log_endpoint
from anubis.utils.http import error_response, success_response, get_number_arg
from anubis.utils.rpc import enqueue_webhook, rpc_enqueue

regrade = Blueprint("admin-regrade", __name__, url_prefix="/admin/regrade")


@regrade.route("/submission/<commit>")
@require_admin()
@log_endpoint("cli", lambda: "regrade-commit")
@json_response
def private_regrade_submission(commit):
    """
    Regrade a specific submission via the unique commit hash.

    :param commit:
    :return:
    """

    # Find the submission
    s = Submission.query.filter(
        Submission.commit == commit,
        Submission.owner_id is not None,
    ).first()
    if s is None:
        return error_response("not found")

    # Reset submission in database
    s.init_submission_models()

    # Enqueue the submission pipeline
    enqueue_webhook(s.id)

    # Return status
    return success_response({"submission": s.data, "user": s.owner.data})


@regrade.route("/<assignment_name>")
@require_admin()
@log_endpoint("cli", lambda: "regrade")
@json_response
def private_regrade_assignment(assignment_name):
    """
    This route is used to restart / re-enqueue jobs.

    The work required for this is potentially very IO entinsive
    on the database. We basically need to load the entire submission
    history out of the database, reset each, then re-enqueue them
    for processing. This makes resetting a single assignment actually
    very time consuming. For this we need to be a bit smart about how to
    handle this.

    We will split all submissions for the given assignment into
    chunks of 100. We can then push each of those chunks as a
    bulk_regrade job to the rpc workers.

    This solution isn't the fastest, but it gets the job done.

    :param assignment_name: name of assignment to regrade
    :return:
    """

    extra = []
    hours = get_number_arg('hours', default_value=-1)
    not_processed = get_number_arg('not_processed', default_value=-1)
    processed = get_number_arg('processed', default_value=-1)
    reaped = get_number_arg('reaped', default_value=-1)

    # Add hours to filter query
    if hours > 0:
        extra.append(
            Submission.created > datetime.now() - timedelta(hours=hours)
        )
    if processed == 1:
        extra.append(
            Submission.processed == True,
        )
    if not_processed == 1:
        extra.append(
            Submission.processed == False,
        )
    if reaped == 1:
        extra.append(
            Submission.state == 'Reaped after timeout',
        )

    # Find the assignment
    assignment = Assignment.query.filter_by(name=assignment_name).first()
    if assignment is None:
        return error_response("cant find assignment")

    # Get all submissions that have an owner (not dangling)
    submissions = Submission.query.filter(
        Submission.assignment_id == assignment.id,
        Submission.owner_id is not None,
        *extra
    ).all()

    # Split the submissions into bite sized chunks
    submission_ids = [s.id for s in submissions]
    submission_chunks = split_chunks(submission_ids, 100)

    # Enqueue each chunk as a job for the rpc workers
    for chunk in submission_chunks:
        rpc_enqueue(rpc_bulk_regrade, 'default', args=[chunk])

    # Pass back the enqueued status
    return success_response({
        "status": "chunks enqueued",
        "submissions": submission_ids,
    })
