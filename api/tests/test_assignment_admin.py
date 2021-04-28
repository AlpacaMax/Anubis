from datetime import datetime, timedelta

from utils import Session, permission_test

sample_sync = {
    "name": "name",
    "course": "CS-UY 3224",
    "hidden": True,
    "github_classroom_url": "",
    "unique_code": "aa11bb22",
    "pipeline_image": "registry.osiris.services/anubis/assignment/aa11bb2233",
    "date": {
        "release": str(datetime.now() - timedelta(hours=2)),
        "due": str(datetime.now() + timedelta(hours=12)),
        "grace": str(datetime.now() + timedelta(hours=13)),
    },
    "description": "This is a very long description that encompasses the entire assignment\n",
    "questions": [
        {"sequence": 1, "questions": [{"q": "What is 3*4?", "a": "12"}, {"q": "What is 3*2", "a": "6"}]},
        {"sequence": 2, "questions": [{"q": "What is sqrt(144)?", "a": "12"}]}
    ],
    "tests": ["abc123"],
}


def test_assignment_admin():
    superuser = Session('superuser')

    permission_test('/admin/assignments/list')

    assignment = superuser.get('/admin/assignments/list')['assignments'][0]
    assignment_id = assignment['id']
    _assignment = superuser.get(f'/admin/assignments/get/{assignment_id}')['assignment']
    assignment_test_id = _assignment['tests'][0]['id']

    permission_test(f'/admin/assignments/get/{assignment_id}')
    permission_test(f'/admin/assignments/assignment/{assignment_id}/questions/get/student')
    permission_test(f'/admin/assignments/tests/toggle-hide/{assignment_test_id}')
    permission_test(f'/admin/assignments/save', method='post', json={'assignment': assignment})
    permission_test(f'/admin/assignments/sync', method='post', json={'assignment': sample_sync})