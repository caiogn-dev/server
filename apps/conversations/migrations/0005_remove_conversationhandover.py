"""
Remove the legacy ConversationHandover model from the conversations app.
Canonical model is in apps.handover.ConversationHandover (table: handover_conversationhandover).
The old table (conversation_handovers) is dropped by this migration.
Uses SeparateDatabaseAndState so this is safe even if the table doesn't exist.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("conversations", "0004_merge"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name="ConversationHandover",
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="DROP TABLE IF EXISTS conversation_handovers CASCADE;",
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
