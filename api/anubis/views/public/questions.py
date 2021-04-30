from flask import Blueprint
from sqlalchemy.exc import IntegrityError, DataError

from anubis.models import db, Assignment, AssignedStudentQuestion, AssignedQuestionResponse, User
from anubis.utils.auth import require_user, current_user
from anubis.utils.http.decorators import json_endpoint, load_from_id, json_response
from anubis.utils.http.https import success_response, error_response
from anubis.utils.lms.course import is_course_admin
from anubis.utils.lms.questions import get_assigned_questions
from anubis.utils.services.elastic import log_endpoint

questions = Blueprint("public-questions", __name__, url_prefix="/public/questions")


@questions.route("/get/<string:id>")
@require_user()
@log_endpoint("public-questions-get", lambda: "get questions")
@load_from_id(Assignment, verify_owner=False)
@json_response
def public_assignment_questions_id(assignment: Assignment):
    """
    Get assigned questions for the current user for a given assignment.

    :param assignment:
    :return:
    """
    # Load current user
    user: User = current_user()

    return success_response({
        "questions": get_assigned_questions(assignment.id, user.id)
    })


@questions.route("/save/<string:id>", methods=["POST"])
@require_user()
@json_endpoint(required_fields=[("response", str)])
def public_questions_save(id: str, response: str):
    """
    Save the response for an assigned question.

    body = {
      response: str
    }

    :param id:
    :return:
    """

    # Get the current user
    user: User = current_user()

    # Try to find the assigned question
    assigned_question = AssignedStudentQuestion.query.filter(
        AssignedStudentQuestion.id == id,
    ).first()

    # Verify that the assigned question they are attempting to update
    # actually exists
    if assigned_question is None:
        return error_response("Assigned question does not exist")

    # Check that the person that the assigned question belongs to the
    # user. If the current user is a course admin (TA, Professor or superuser)
    # then we can skip this check.
    if not is_course_admin(user.id) and assigned_question.owner_id != user.id:
        return error_response("Assigned question does not exist")

    # Verify that the response is a string object
    if not isinstance(response, str):
        return error_response('response must be a string')

    # Create a new response
    res = AssignedQuestionResponse(
        assigned_question_id=assigned_question.id,
        response=response
    )

    # Add the response to the session
    db.session.add(res)

    try:
        # Try to commit the response
        db.session.commit()
    except (IntegrityError, DataError):
        # If the response they gave was too long then a DataError will
        # be raised. The max length for the mariadb TEXT type is something
        # like 2^16 characters. If they hit this limit, then they are doing
        # something wrong.
        return error_response("Server was unable to save your response.")

    return success_response({
        "status": "Response Saved",
    })
