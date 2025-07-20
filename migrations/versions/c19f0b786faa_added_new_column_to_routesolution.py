"""Added new column to RouteSolution

Revision ID: c19f0b786faa
Revises: 11ecb2624d10
Create Date: 2025-07-19 17:24:35.670931

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c19f0b786faa'
down_revision = '11ecb2624d10'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("route_solution") as batch_op:
        batch_op.add_column(
            sa.Column(
                "needs_refresh",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0")     # ← SQLite wants this
            )
        )

def downgrade():
    with op.batch_alter_table("route_solution") as batch_op:
        batch_op.drop_column("needs_refresh")


    # ### end Alembic commands ###
