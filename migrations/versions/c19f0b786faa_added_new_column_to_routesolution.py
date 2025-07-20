from alembic import op
import sqlalchemy as sa

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
                server_default=sa.false()
            )
        )

def downgrade():
    with op.batch_alter_table("route_solution") as batch_op:
        batch_op.drop_column("needs_refresh")
