import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
import sys
_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _here not in sys.path:
    sys.path.insert(0, _here)
django.setup()

import asyncio
import importlib
import json
import unittest


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestScaffold(unittest.TestCase):
    def setUp(self):
        os.environ['MCP_DB_SAFE_MODE'] = 'true'
        import mcp_database
        importlib.reload(mcp_database)
        self.mod = mcp_database

    def test_26_tools_registered(self):
        tools = run(self.mod.list_tools())
        self.assertEqual(len(tools), 26)

    def test_tool_names(self):
        tools = run(self.mod.list_tools())
        names = {t.name for t in tools}
        expected = {
            'list_tables', 'table_schema', 'table_stats', 'explain_query',
            'table_indexes', 'compare_model_vs_table',
            'schema_overview', 'model_detail', 'find_field', 'relationship_graph',
            'migration_status', 'make_migrations', 'run_migrations', 'show_migration_sql',
            'count_records', 'sample_records', 'run_sql',
            'integrity_report', 'find_orphans', 'find_duplicates', 'check_nulls',
            'find_ghost_users', 'customer_identity_audit', 'stats_drift_check',
            'security_audit', 'pgvector_readiness',
        }
        self.assertEqual(names, expected)

    def test_unknown_tool_returns_error(self):
        result = run(self.mod.call_tool('nonexistent_tool', {}))
        self.assertIn('error', result[0].text)

    def test_mask_sensitive_redacts_in_safe_mode(self):
        record = {'name': 'João', 'api_key': 'secret123', 'email': 'a@b.com'}
        masked = self.mod._mask_sensitive(record)
        self.assertEqual(masked['api_key'], '***REDACTED***')
        self.assertEqual(masked['name'], 'João')

    def test_mask_sensitive_passthrough_when_safe_mode_off(self):
        os.environ['MCP_DB_SAFE_MODE'] = 'false'
        import mcp_database
        importlib.reload(mcp_database)
        record = {'api_key': 'secret123'}
        masked = mcp_database._mask_sensitive(record)
        self.assertEqual(masked['api_key'], 'secret123')

    def test_safe_mode_blocks_write_without_confirm(self):
        result = run(self.mod.call_tool('run_sql', {'sql': 'UPDATE stores_store SET name=%s WHERE id=1', 'params': ['x']}))
        data = json.loads(result[0].text)
        self.assertIn('error', data)
        self.assertIn('confirm', data['error'])

    def test_safe_mode_blocks_drop_even_with_confirm(self):
        result = run(self.mod.call_tool('run_sql', {'sql': 'DROP TABLE stores_store', 'confirm': True}))
        data = json.loads(result[0].text)
        self.assertIn('error', data)
        self.assertIn('bloqueado', data['error'])

    def test_make_migrations_requires_confirm_in_safe_mode(self):
        result = run(self.mod.call_tool('make_migrations', {}))
        data = json.loads(result[0].text)
        self.assertIn('error', data)
        self.assertIn('confirm', data['error'])

    def test_run_migrations_requires_confirm_in_safe_mode(self):
        result = run(self.mod.call_tool('run_migrations', {}))
        data = json.loads(result[0].text)
        self.assertIn('error', data)
        self.assertIn('confirm', data['error'])


if __name__ == '__main__':
    unittest.main()
