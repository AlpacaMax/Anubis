from flask import Blueprint

from anubis.utils.auth import require_superuser
from anubis.utils.data import is_debug
from anubis.utils.http.decorators import json_response
from anubis.utils.http.https import success_response, error_response
from anubis.utils.services.rpc import enqueue_seed

seed = Blueprint("admin-seed", __name__, url_prefix="/admin/seed")


@seed.route("/")
@require_superuser(unless_debug=True)
@json_response
def admin_seed():
    """
    Seed debug data.

    :return:
    """

    # Only allow seed to run if in debug mode
    if not is_debug():
        return error_response('Seed only enabled in debug mode')

    # Enqueue a seed job
    enqueue_seed()

    # Return the status
    return success_response({
        'status': 'enqueued seed'
    })
