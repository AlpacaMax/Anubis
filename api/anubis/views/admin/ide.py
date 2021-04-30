import json
from datetime import datetime

from flask import Blueprint

from anubis.models import db, TheiaSession
from anubis.rpc.theia import reap_all_theia_sessions
from anubis.utils.auth import require_admin, current_user
from anubis.utils.http.decorators import json_response, json_endpoint
from anubis.utils.http.https import success_response, error_response
from anubis.utils.lms.course import get_course_context
from anubis.utils.services.elastic import log_endpoint
from anubis.utils.services.rpc import enqueue_ide_initialize
from anubis.utils.services.rpc import rpc_enqueue, enqueue_ide_stop

ide = Blueprint("admin-ide", __name__, url_prefix="/admin/ide")


@ide.route("/initialize", methods=["POST"])
@ide.route("/initialize-custom", methods=["POST"])
@require_admin()
@log_endpoint("admin-ide-initialize")
@json_endpoint([('settings', dict)])
def admin_ide_initialize_custom(settings: dict, **_):
    """
    Initialize a new management ide with options.

    :param settings:
    :param _:
    :return:
    """

    # Get the current user
    user = current_user()

    # Get the current course context
    course = get_course_context()

    # Check to see if there is already a management session
    # allocated for the current user
    session = TheiaSession.query.filter(
        TheiaSession.active,
        TheiaSession.owner_id == user.id,
        TheiaSession.course_id == course.id,
        TheiaSession.assignment_id == None,
    ).first()

    # If there is already a session, then stop
    if session is not None:
        return success_response({"session": session.data})

    # Read the options out of the posted data
    network_locked = settings.get('network_locked', False)
    privileged = settings.get('privileged', True)
    image = settings.get('image', 'registry.osiris.services/anubis/theia-admin')
    repo_url = settings.get('repo_url', 'https://github.com/os3224/anubis-assignment-tests')
    options_str = settings.get('options', '{"limits": {"cpu": "4", "memory": "4Gi"}}')

    # Attempt to load the options_str into a dict object
    try:
        options = json.loads(options_str)
    except json.JSONDecodeError:
        return error_response('Can not parse JSON options')

    # Create a new session
    session = TheiaSession(
        owner_id=user.id, assignment_id=None, course_id=course.id,
        network_locked=network_locked, privileged=privileged,
        image=image, repo_url=repo_url, options=options,
        active=True, state="Initializing",
    )
    db.session.add(session)
    db.session.commit()

    # Send kube resource initialization rpc job
    enqueue_ide_initialize(session.id)

    return success_response({
        "session": session.data,
        "settings": session.settings,
        "status": "Admin IDE Initialized."
    })


@ide.route("/active")
@require_admin()
@log_endpoint("admin-ide-active")
@json_response
def admin_ide_active():
    """
    Get the list of all active Theia ides within
    the current course context.

    :return:
    """

    # Get the current user
    user = current_user()

    # Get the course context
    course = get_course_context()

    # Query for an active theia session within this course context
    session = TheiaSession.query.filter(
        TheiaSession.active,
        TheiaSession.owner_id == user.id,
        TheiaSession.course_id == course.id,
        TheiaSession.assignment_id == None,
    ).first()

    # If there was no session, then stop
    if session is None:
        return success_response({"session": None})

    # Return the active session informatino
    return success_response({
        "session": session.data,
        "settings": session.settings,
    })


@ide.route("/list")
@require_admin()
@log_endpoint("ide-list")
@json_response
def admin_ide_list():
    """
    List all active ide sessions

    :return:
    """

    course = get_course_context()

    # Get all active sessions
    sessions = TheiaSession.query.filter(
        TheiaSession.active == True,
        TheiaSession.course_id == course.id,
    ).all()

    # Hand back response
    return success_response({"sessions": [session.data for session in sessions]})


@ide.route("/stop/<string:id>")
@require_admin()
@log_endpoint("ide-end")
@json_response
def admin_ide_stop_id(id: str):
    """
    List all active ide sessions

    :return:
    """

    course = get_course_context()

    session = TheiaSession.query.filter(
        TheiaSession.id == id,
        TheiaSession.course_id == course.id,
    ).first()

    if session is None:
        return error_response("Session does not exist.")

    session.active = False
    session.ended = datetime.now()
    session.state = "Ending"
    db.session.commit()

    enqueue_ide_stop(session.id)

    # Hand back response
    return success_response({"status": "Session Killed."})


@ide.route("/reap-all")
@require_admin()
@log_endpoint("ide-reap-all")
@json_response
def private_ide_reap_all():
    """
    Enqueue a job for the rpc workers to reap all the active
    theia submissions. They will end all active sessions in the
    database, then schedule all the kube resources for deletion.

    :return:
    """

    course = get_course_context()

    # Send reap job to rpc cluster
    rpc_enqueue(reap_all_theia_sessions, 'theia', args=(course.id,))

    # Hand back status
    return success_response(
        {"status": "Reap job enqueued. Session cleanup will take a minute."}
    )
