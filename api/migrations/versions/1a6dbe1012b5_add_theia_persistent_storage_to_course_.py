"""ADD theia_persistent_storage to course options

Revision ID: 1a6dbe1012b5
Revises: ba7750bc4d14
Create Date: 2021-08-10 21:53:08.735987

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "1a6dbe1012b5"
down_revision = "ba7750bc4d14"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "course",
        sa.Column("theia_persistent_storage", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "course",
        sa.Column("github_repo_required", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "assignment",
        sa.Column("theia_persistent_storage", sa.Boolean(), nullable=True),
    )
    conn = op.get_bind()
    with conn.begin():
        conn.execute("update course set theia_persistent_storage = 0;")
        conn.execute("update course set github_repo_required = 0;")
        conn.execute("update assignment set theia_persistent_storage = 0;")
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("course", "theia_persistent_storage")
    op.drop_column("course", "github_repo_required")
    op.drop_column("assignment", "theia_persistent_storage")
    # ### end Alembic commands ###
