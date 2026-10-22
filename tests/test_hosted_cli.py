"""Synthetic frozen-contract HTTP tests; no accounts or external hosts."""
import copy
import hashlib
import http.server
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse

KIT = Path(__file__).resolve().parents[1] / 'board/kit/keeptrack.py'
BOARD_ID = '30000000-0000-4000-8000-000000000001'
ACTOR = {'user_id': '10000000-0000-4000-8000-000000000001', 'agent_id': '20000000-0000-4000-8000-000000000001'}


# Copied from frozen 8128b59 synthetic fixtures/OpenAPI; no live board content.
FIXTURE_FILES = {'tasks.json': {'version': 4, 'layout': 'split', 'next_num': 900000, 'columns': [{'id': 'backlog', 'name': 'Backlog'}, {'id': 'todo', 'name': 'To do'}, {'id': 'in-progress', 'name': 'In progress'}, {'id': 'pending-review', 'name': 'Pending review'}, {'id': 'done', 'name': 'Done'}], 'people': [{'github': 'synthetic-a', 'name': 'Example A'}, {'github': 'synthetic-b', 'name': 'Example B'}], 'settings': {'max_agent_claims': 2, 'stale_after_minutes': 30, 'review_inbox': {'enabled': True}}, 'archive': {'files': {'2025': {'tasks': 1, 'contacts': 0}}}, 'x-synthetic': {'absent-is-not-null': None, 'ordered': [2, 1]}, 'x-keeptrack-hosted-attribution': {'version': 1, 'records': {'cards/t_sample.json#': {'createdBy': {'user_id': '10000000-0000-4000-8000-000000000001', 'agent_id': '20000000-0000-4000-8000-000000000001'}, 'updatedBy': {'user_id': '10000000-0000-4000-8000-000000000001', 'agent_id': '20000000-0000-4000-8000-000000000001'}}, 'archive/2025.json#/tasks/0': {'createdBy': {'user_id': '10000000-0000-4000-8000-000000000001', 'agent_id': '20000000-0000-4000-8000-000000000001'}, 'updatedBy': {'user_id': '10000000-0000-4000-8000-000000000001', 'agent_id': '20000000-0000-4000-8000-000000000001'}, 'on_behalf_of': '10000000-0000-4000-8000-000000000002'}, 'archive/2025.json#/tasks/0/comments/0': {'createdBy': {'user_id': '10000000-0000-4000-8000-000000000001', 'agent_id': '20000000-0000-4000-8000-000000000001'}, 'updatedBy': {'user_id': '10000000-0000-4000-8000-000000000001', 'agent_id': '20000000-0000-4000-8000-000000000001'}, 'on_behalf_of': '10000000-0000-4000-8000-000000000002'}}, 'changes': [{'actor': {'user_id': '10000000-0000-4000-8000-000000000001', 'agent_id': '20000000-0000-4000-8000-000000000001'}, 'command': 'claim', 'at': '2026-01-02T03:04:05.000+00:00', 'on_behalf_of': '10000000-0000-4000-8000-000000000002', 'paths': ['archive/2025.json']}]}}, 'cards/t_sample.json': {'id': 't_sample', 'num': 17, 'title': 'Synthetic contract sample', 'column': 'backlog', 'rank': 'a0', 'details': 'Only invented content.', 'assignees': ['synthetic-a'], 'todos': [{'id': 'd_one', 'text': 'Check synthetic example', 'done': False}], 'links': [], 'contacts': ['p_sample'], 'project': 'pr_sample', 'value': 4, 'effort': 'M', 'created': '2026-01-02T03:04:05.000+00:00', 'updated': '2026-01-02T03:04:05.000+00:00', 'comments': [{'id': 'c_one', 'text': 'Invented comment', 'by': 'example-agent@synthetic-a', 'at': '2026-01-02T03:04:05.000+00:00', 'actor': {'user_id': '10000000-0000-4000-8000-000000000001', 'agent_id': '20000000-0000-4000-8000-000000000001'}}], 'history': [{'at': '2026-01-02T03:04:05.000+00:00', 'by': 'example-agent@synthetic-a', 'text': 'Created', 'actor': {'user_id': '10000000-0000-4000-8000-000000000001', 'agent_id': '20000000-0000-4000-8000-000000000001'}}], 'x-sample': {'null': None, 'ordered': [3, 1, 2]}}, 'people/p_sample.json': {'id': 'p_sample', 'name': 'Synthetic Person', 'company': 'Example Company', 'stage': 'New', 'next': 'Review invented material', 'next_due': '2026-02-01', 'links': [], 'comments': [], 'history': [], 'x-sample': None}, 'projects/pr_sample.json': {'id': 'pr_sample', 'name': 'Synthetic Project', 'client': 'Example Company', 'people': ['p_sample'], 'status': 'active', 'links': []}, 'proposals/r_sample.json': {'id': 'r_sample', 'version': 1, 'kind': 'task.create', 'status': 'pending', 'title': 'Synthetic proposal', 'action_key': 'synthetic-action', 'work_key': 'synthetic-work', 'change': {'title': 'Invented task'}, 'target': None, 'decision': None, 'history': [], 'createdBy': 'legacy-example'}, 'archive/2025.json': {'version': 3, 'archive': True, 'year': '2025', 'tasks': [{'id': 't_old', 'num': 2, 'title': 'Synthetic contract sample', 'column': 'done', 'rank': 'a0', 'details': 'Only invented content.', 'assignees': ['synthetic-a'], 'todos': [], 'links': [], 'contacts': [], 'project': '', 'value': 4, 'effort': 'M', 'created': '2026-01-02T03:04:05.000+00:00', 'updated': '2026-01-02T03:04:05.000+00:00', 'comments': [{'id': 'c_old', 'text': 'Archived invented comment', 'at': '2026-01-02T03:04:05.000+00:00', 'actor': {'user_id': '10000000-0000-4000-8000-000000000001', 'agent_id': '20000000-0000-4000-8000-000000000001'}, 'on_behalf_of': '10000000-0000-4000-8000-000000000002'}], 'history': [], 'x-sample': {'null': None, 'ordered': [3, 1, 2]}}], 'contacts': [], 'history': {'t_old': [{'at': '2026-01-02T03:04:05.000+00:00', 'text': 'Old history', 'actor': {'user_id': '10000000-0000-4000-8000-000000000001', 'agent_id': '20000000-0000-4000-8000-000000000001'}, 'on_behalf_of': '10000000-0000-4000-8000-000000000002'}]}, 'x-preserve': {'empty': [], 'null': None}}}
SCHEMAS = {'Actor': {'type': 'object', 'properties': {'user_id': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'}, 'agent_id': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 'nullable': True}}, 'additionalProperties': False, 'required': ['user_id', 'agent_id']}, 'Scope': {'type': 'string', 'enum': ['read', 'write', 'claim', 'approve']}, 'Role': {'type': 'string', 'enum': ['owner', 'editor', 'viewer']}, 'Revision': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'Cursor': {'type': 'string', 'minLength': 1, 'description': 'Opaque board/epoch/commit-ordered sequence cursor.'}, 'Bigint': {'type': 'string', 'pattern': '^[1-9][0-9]*$'}, 'VirtualPath': {'type': 'string', 'pattern': '^(tasks\\.json|(?:cards|people|projects|proposals)/[A-Za-z0-9][A-Za-z0-9_-]{0,63}\\.json|archive/[0-9]{4}\\.json)$'}, 'FileMap': {'type': 'object', 'additionalProperties': {}}, 'Omitted': {'type': 'array', 'items': {'type': 'string', 'enum': ['history', 'comments']}}, 'CardWithoutNum': {'type': 'object', 'properties': {'id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'title': {'type': 'string', 'minLength': 1}, 'details': {'type': 'string'}, 'assignees': {'type': 'array', 'items': {'type': 'string'}}, 'todos': {'type': 'array', 'items': {'type': 'object', 'properties': {'id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'text': {'type': 'string'}, 'done': {'type': 'boolean'}}, 'additionalProperties': False, 'required': ['id', 'text', 'done']}}, 'links': {'type': 'array', 'items': {'type': 'object', 'properties': {'url': {'type': 'string', 'minLength': 1}, 'title': {'type': 'string'}}, 'additionalProperties': False, 'required': ['url']}}, 'column': {'type': 'string', 'enum': ['backlog']}, 'rank': {'type': 'string', 'minLength': 1}, 'after': {'type': 'array', 'items': {'type': 'string'}}, 'extensions': {'type': 'object', 'additionalProperties': {}}, 'client': {'type': 'string'}, 'project': {'type': 'string'}, 'due': {'type': 'string'}, 'priority': {'type': 'string'}, 'labels': {'type': 'array', 'items': {'type': 'string'}}}, 'additionalProperties': True, 'required': ['id', 'title', 'assignees'], 'description': 'Complete schema-4 card input except server-owned num/lifecycle/attribution fields. Extensions at identical keys are preserved. Protected keys rejected before mutation.'}, 'Fence': {'type': 'object', 'properties': {'session_id': {'type': 'string', 'minLength': 1}, 'fence': {'type': 'string', 'pattern': '^[1-9][0-9]*$'}, 'proof': {'type': 'string', 'pattern': '^[0-9a-f]{64}$', 'description': '256-bit random proof encoded as lowercase hex. Never log/export.'}}, 'additionalProperties': False, 'required': ['session_id', 'fence', 'proof']}, 'ClaimRequest': {'type': 'object', 'properties': {'session_id': {'type': 'string', 'minLength': 1}, 'attended': {'type': 'boolean'}, 'proof_digest': {'type': 'string', 'pattern': '^[0-9a-f]{64}$', 'description': 'SHA-256 of decoded random proof bytes, lowercase hex.'}, 'on_behalf_of': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'}}, 'additionalProperties': False, 'required': ['session_id', 'attended', 'proof_digest']}, 'ClaimView': {'type': 'object', 'properties': {'card_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'actor': {'$ref': '#/components/schemas/Actor'}, 'session_id': {'type': 'string', 'minLength': 1}, 'fence': {'type': 'string', 'pattern': '^[1-9][0-9]*$'}, 'attended': {'type': 'boolean'}, 'status': {'type': 'string', 'enum': ['running', 'blocked', 'stuck', 'released', 'done']}, 'expires_at': {'type': 'string', 'minLength': 1}, 'live': {'type': 'boolean'}, 'on_behalf_of': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'}}, 'additionalProperties': False, 'required': ['card_id', 'actor', 'session_id', 'fence', 'attended', 'status', 'expires_at', 'live']}, 'PutChange': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['put']}, 'path': {'$ref': '#/components/schemas/VirtualPath'}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.', 'nullable': True}, 'body': {}}, 'additionalProperties': False, 'required': ['kind', 'path', 'baseRev', 'body']}, 'DeleteChange': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['delete']}, 'path': {'$ref': '#/components/schemas/VirtualPath'}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}}, 'additionalProperties': False, 'required': ['kind', 'path', 'baseRev']}, 'CreateCardCommand': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['create-card']}, 'card': {'$ref': '#/components/schemas/CardWithoutNum'}, 'claim': {'$ref': '#/components/schemas/ClaimRequest'}}, 'additionalProperties': False, 'required': ['kind', 'card']}, 'Change': {'oneOf': [{'$ref': '#/components/schemas/PutChange'}, {'$ref': '#/components/schemas/DeleteChange'}, {'$ref': '#/components/schemas/CreateCardCommand'}]}, 'CommitRequest': {'type': 'object', 'properties': {'ops': {'type': 'array', 'items': {'$ref': '#/components/schemas/Change'}, 'minItems': 1}, 'fences': {'type': 'object', 'additionalProperties': {'$ref': '#/components/schemas/Fence'}}}, 'additionalProperties': False, 'required': ['ops']}, 'ClaimCommand': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['claim']}, 'card_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'session_id': {'type': 'string', 'minLength': 1}, 'attended': {'type': 'boolean'}, 'proof_digest': {'type': 'string', 'pattern': '^[0-9a-f]{64}$', 'description': 'SHA-256 of decoded random proof bytes, lowercase hex.'}, 'on_behalf_of': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'}, 'takeover': {'type': 'boolean'}}, 'additionalProperties': False, 'required': ['kind', 'card_id', 'baseRev', 'session_id', 'attended', 'proof_digest']}, 'HeartbeatCommand': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['heartbeat']}, 'card_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'session_id': {'type': 'string', 'minLength': 1}, 'fence': {'type': 'string', 'pattern': '^[1-9][0-9]*$'}, 'proof': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}, 'status': {'type': 'string', 'enum': ['running', 'blocked', 'stuck']}, 'note': {'type': 'string'}}, 'additionalProperties': False, 'required': ['kind', 'card_id', 'baseRev', 'session_id', 'fence', 'proof', 'status']}, 'ReleaseCommand': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['release']}, 'card_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'session_id': {'type': 'string', 'minLength': 1}, 'fence': {'type': 'string', 'pattern': '^[1-9][0-9]*$'}, 'proof': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}, 'column': {'type': 'string', 'enum': ['todo', 'backlog']}}, 'additionalProperties': False, 'required': ['kind', 'card_id', 'baseRev', 'session_id', 'fence', 'proof'], 'description': 'Default todo only restores an existing approval; otherwise backlog. Ends lease and advances fence.'}, 'MoveCommand': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['move']}, 'card_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'column': {'type': 'string', 'minLength': 1}, 'holder': {'$ref': '#/components/schemas/Fence'}}, 'additionalProperties': False, 'required': ['kind', 'card_id', 'baseRev', 'column']}, 'DoneCommand': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['done']}, 'card_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'holder': {'$ref': '#/components/schemas/Fence'}, 'note': {'type': 'string', 'minLength': 1}, 'pr': {'type': 'object', 'properties': {'url': {'type': 'string', 'minLength': 1}, 'state': {'type': 'string', 'enum': ['merged', 'open', 'unknown']}}, 'additionalProperties': False, 'required': ['url', 'state']}, 'cancel': {'type': 'boolean'}}, 'additionalProperties': False, 'required': ['kind', 'card_id', 'baseRev', 'note']}, 'ReviewCommand': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['review']}, 'card_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'holder': {'$ref': '#/components/schemas/Fence'}, 'note': {'type': 'string', 'minLength': 1}}, 'additionalProperties': False, 'required': ['kind', 'card_id', 'baseRev', 'note']}, 'ApproveCommand': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['approve']}, 'card_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}}, 'additionalProperties': False, 'required': ['kind', 'card_id', 'baseRev']}, 'ArchiveCommand': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['archive']}, 'entity_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'rootRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'archiveRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.', 'nullable': True}, 'year': {'type': 'string', 'pattern': '^[0-9]{4}$'}, 'holder': {'$ref': '#/components/schemas/Fence'}}, 'additionalProperties': False, 'required': ['kind', 'entity_id', 'baseRev', 'rootRev', 'archiveRev', 'year']}, 'UnarchiveCommand': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['unarchive']}, 'entity_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'rootRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'archiveRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.', 'nullable': True}, 'year': {'type': 'string', 'pattern': '^[0-9]{4}$'}, 'holder': {'$ref': '#/components/schemas/Fence'}}, 'additionalProperties': False, 'required': ['kind', 'entity_id', 'baseRev', 'rootRev', 'archiveRev', 'year']}, 'CommentCommand': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['comment']}, 'card_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'text': {'type': 'string', 'minLength': 1}}, 'additionalProperties': False, 'required': ['kind', 'card_id', 'baseRev', 'text']}, 'ProposalAddCommand': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['proposal-add']}, 'proposal': {'type': 'object', 'additionalProperties': {}}}, 'additionalProperties': False, 'required': ['kind', 'proposal']}, 'DecisionCommand': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['decision']}, 'statement': {'type': 'string', 'minLength': 1}}, 'additionalProperties': False, 'required': ['kind', 'statement']}, 'Command': {'oneOf': [{'$ref': '#/components/schemas/CreateCardCommand'}, {'$ref': '#/components/schemas/ClaimCommand'}, {'$ref': '#/components/schemas/HeartbeatCommand'}, {'$ref': '#/components/schemas/ReleaseCommand'}, {'$ref': '#/components/schemas/MoveCommand'}, {'$ref': '#/components/schemas/DoneCommand'}, {'$ref': '#/components/schemas/ReviewCommand'}, {'$ref': '#/components/schemas/ApproveCommand'}, {'$ref': '#/components/schemas/ArchiveCommand'}, {'$ref': '#/components/schemas/UnarchiveCommand'}, {'$ref': '#/components/schemas/CommentCommand'}, {'$ref': '#/components/schemas/ProposalAddCommand'}, {'$ref': '#/components/schemas/DecisionCommand'}], 'description': 'proposal-add and decision are phase 1b and fail with capability_unavailable before mutation in phase 0. Conditional holder requirements are enforced transactionally.'}, 'FileResult': {'type': 'object', 'properties': {'path': {'$ref': '#/components/schemas/VirtualPath'}, 'body': {}, 'rev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'createdBy': {'$ref': '#/components/schemas/Actor'}, 'updatedBy': {'$ref': '#/components/schemas/Actor'}}, 'additionalProperties': False, 'required': ['path', 'body', 'rev', 'createdBy', 'updatedBy']}, 'FileUpdate': {'type': 'object', 'properties': {'path': {'$ref': '#/components/schemas/VirtualPath'}, 'rev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.', 'nullable': True}, 'body': {}}, 'additionalProperties': False, 'required': ['path', 'rev']}, 'CommitResult': {'type': 'object', 'properties': {'cursor': {'type': 'string', 'minLength': 1, 'description': 'Opaque board/epoch/commit-ordered sequence cursor.'}, 'files': {'type': 'array', 'items': {'$ref': '#/components/schemas/FileUpdate'}}}, 'additionalProperties': False, 'required': ['cursor', 'files']}, 'ClaimResult': {'type': 'object', 'properties': {'fence': {'type': 'string', 'pattern': '^[1-9][0-9]*$'}, 'expires_at': {'type': 'string', 'minLength': 1}, 'on_behalf_of': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'}}, 'additionalProperties': False, 'required': ['fence', 'expires_at']}, 'CreatedCardResult': {'type': 'object', 'properties': {'card_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'num': {'type': 'integer', 'minimum': 1, 'maximum': 9007199254740991}, 'claim': {'$ref': '#/components/schemas/ClaimResult'}}, 'additionalProperties': False, 'required': ['card_id', 'num']}, 'LifecycleResult': {'type': 'object', 'properties': {'card_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'column': {'type': 'string', 'minLength': 1}, 'claim_ended': {'type': 'boolean'}}, 'additionalProperties': False, 'required': ['card_id', 'column', 'claim_ended']}, 'ArchiveResult': {'type': 'object', 'properties': {'entity_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'year': {'type': 'string', 'pattern': '^[0-9]{4}$'}, 'archived': {'type': 'boolean'}}, 'additionalProperties': False, 'required': ['entity_id', 'year', 'archived']}, 'CommentResult': {'type': 'object', 'properties': {'comment_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'actor': {'$ref': '#/components/schemas/Actor'}, 'at': {'type': 'string', 'minLength': 1}}, 'additionalProperties': False, 'required': ['comment_id', 'actor', 'at']}, 'CommandResult': {'type': 'object', 'properties': {'cursor': {'type': 'string', 'minLength': 1, 'description': 'Opaque board/epoch/commit-ordered sequence cursor.'}, 'files': {'type': 'array', 'items': {'$ref': '#/components/schemas/FileUpdate'}}, 'result': {'oneOf': [{'$ref': '#/components/schemas/ClaimResult'}, {'$ref': '#/components/schemas/CreatedCardResult'}, {'$ref': '#/components/schemas/LifecycleResult'}, {'$ref': '#/components/schemas/ArchiveResult'}, {'$ref': '#/components/schemas/CommentResult'}]}}, 'additionalProperties': False, 'required': ['cursor', 'files', 'result']}, 'Identity': {'type': 'object', 'properties': {'user_id': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'}, 'agent_id': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 'nullable': True}, 'boards': {'type': 'array', 'items': {'type': 'object', 'properties': {'id': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'}, 'role': {'$ref': '#/components/schemas/Role'}, 'handle': {'type': 'string', 'minLength': 1}}, 'additionalProperties': False, 'required': ['id', 'role', 'handle']}}, 'token_scopes': {'type': 'array', 'items': {'$ref': '#/components/schemas/Scope'}}}, 'additionalProperties': False, 'required': ['user_id', 'agent_id', 'boards', 'token_scopes']}, 'Capabilities': {'type': 'object', 'properties': {'casWrites': {'type': 'boolean'}, 'atomicMultiFile': {'type': 'boolean'}, 'changeFeed': {'type': 'boolean'}, 'phase': {'type': 'string', 'enum': ['0']}, 'lazyHistory': {'type': 'boolean'}, 'teamDocuments': {'type': 'boolean'}, 'commands': {'type': 'array', 'items': {'type': 'string'}}}, 'additionalProperties': False, 'required': ['casWrites', 'atomicMultiFile', 'changeFeed', 'phase', 'lazyHistory', 'teamDocuments', 'commands']}, 'EntityView': {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['card', 'person', 'project', 'proposal']}, 'body': {'type': 'object', 'additionalProperties': {}}, 'rev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'omitted': {'$ref': '#/components/schemas/Omitted'}, 'createdBy': {'$ref': '#/components/schemas/Actor'}, 'updatedBy': {'$ref': '#/components/schemas/Actor'}}, 'additionalProperties': False, 'required': ['kind', 'body', 'rev', 'createdBy', 'updatedBy']}, 'RootView': {'type': 'object', 'properties': {'body': {'type': 'object', 'additionalProperties': {}}, 'rev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'createdBy': {'$ref': '#/components/schemas/Actor'}, 'updatedBy': {'$ref': '#/components/schemas/Actor'}}, 'additionalProperties': False, 'required': ['body', 'rev', 'createdBy', 'updatedBy']}, 'Snapshot': {'type': 'object', 'properties': {'schema': {'type': 'integer', 'enum': [4]}, 'board_id': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'}, 'root': {'$ref': '#/components/schemas/RootView'}, 'entities': {'type': 'array', 'items': {'$ref': '#/components/schemas/EntityView'}}, 'claims': {'type': 'array', 'items': {'$ref': '#/components/schemas/ClaimView'}}, 'cursor': {'type': 'string', 'minLength': 1, 'description': 'Opaque board/epoch/commit-ordered sequence cursor.'}, 'capabilities': {'$ref': '#/components/schemas/Capabilities'}}, 'additionalProperties': False, 'required': ['schema', 'board_id', 'root', 'entities', 'claims', 'cursor', 'capabilities']}, 'FileDelta': {'type': 'object', 'properties': {'resource': {'type': 'string', 'enum': ['file']}, 'path': {'$ref': '#/components/schemas/VirtualPath'}, 'rev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.', 'nullable': True}, 'op': {'type': 'string', 'enum': ['upsert', 'delete']}, 'body': {}, 'omitted': {'$ref': '#/components/schemas/Omitted'}}, 'additionalProperties': False, 'required': ['resource', 'path', 'rev', 'op']}, 'DocumentDelta': {'type': 'object', 'properties': {'resource': {'type': 'string', 'enum': ['document']}, 'id': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'}, 'rev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.', 'nullable': True}, 'op': {'type': 'string', 'enum': ['upsert', 'delete']}}, 'additionalProperties': False, 'required': ['resource', 'id', 'rev', 'op']}, 'DeltaBatch': {'type': 'object', 'properties': {'cursor': {'type': 'string', 'minLength': 1, 'description': 'Opaque board/epoch/commit-ordered sequence cursor.'}, 'changes': {'type': 'array', 'items': {'oneOf': [{'$ref': '#/components/schemas/FileDelta'}, {'$ref': '#/components/schemas/DocumentDelta'}]}}, 'claims': {'type': 'array', 'items': {'$ref': '#/components/schemas/ClaimView'}}}, 'additionalProperties': False, 'required': ['cursor', 'changes']}, 'DeltaPage': {'type': 'object', 'properties': {'through': {'type': 'string', 'minLength': 1, 'description': 'Opaque board/epoch/commit-ordered sequence cursor.'}, 'has_more': {'type': 'boolean'}, 'batches': {'type': 'array', 'items': {'$ref': '#/components/schemas/DeltaBatch'}}}, 'additionalProperties': False, 'required': ['through', 'has_more', 'batches']}, 'Eligibility': {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': ['approve', 'claim']}, 'card_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'}, 'eligible': {'type': 'boolean'}, 'reasons': {'type': 'array', 'items': {'type': 'string'}}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'on_behalf_of': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'}}, 'additionalProperties': False, 'required': ['action', 'card_id', 'eligible', 'reasons', 'baseRev']}, 'DocumentPut': {'type': 'object', 'properties': {'name': {'type': 'string', 'minLength': 1}, 'body': {'type': 'object', 'additionalProperties': {}}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.', 'nullable': True}}, 'additionalProperties': False, 'required': ['name', 'body', 'baseRev']}, 'DocumentDelete': {'type': 'object', 'properties': {'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}}, 'additionalProperties': False, 'required': ['baseRev']}, 'Document': {'type': 'object', 'properties': {'id': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'}, 'name': {'type': 'string', 'minLength': 1}, 'body': {'type': 'object', 'additionalProperties': {}}, 'rev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'createdBy': {'$ref': '#/components/schemas/Actor'}, 'updatedBy': {'$ref': '#/components/schemas/Actor'}}, 'additionalProperties': False, 'required': ['id', 'name', 'body', 'rev', 'createdBy', 'updatedBy']}, 'DocumentList': {'type': 'object', 'properties': {'documents': {'type': 'array', 'items': {'$ref': '#/components/schemas/Document'}}, 'cursor': {'type': 'string', 'minLength': 1, 'description': 'Opaque board/epoch/commit-ordered sequence cursor.'}}, 'additionalProperties': False, 'required': ['documents', 'cursor']}, 'DocumentWriteResult': {'type': 'object', 'properties': {'cursor': {'type': 'string', 'minLength': 1, 'description': 'Opaque board/epoch/commit-ordered sequence cursor.'}, 'document': {'$ref': '#/components/schemas/Document'}}, 'additionalProperties': False, 'required': ['cursor', 'document']}, 'DeleteResult': {'type': 'object', 'properties': {'cursor': {'type': 'string', 'minLength': 1, 'description': 'Opaque board/epoch/commit-ordered sequence cursor.'}}, 'additionalProperties': False, 'required': ['cursor']}, 'GrantPut': {'type': 'object', 'properties': {'scopes': {'type': 'array', 'items': {'$ref': '#/components/schemas/Scope'}}, 'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.', 'nullable': True}}, 'additionalProperties': False, 'required': ['scopes', 'baseRev']}, 'GrantDelete': {'type': 'object', 'properties': {'baseRev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}}, 'additionalProperties': False, 'required': ['baseRev']}, 'GrantResult': {'type': 'object', 'properties': {'cursor': {'type': 'string', 'minLength': 1, 'description': 'Opaque board/epoch/commit-ordered sequence cursor.'}, 'agent_id': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'}, 'scopes': {'type': 'array', 'items': {'$ref': '#/components/schemas/Scope'}}, 'rev': {'type': 'string', 'minLength': 1, 'description': 'Opaque revision. Never parse or compare numerically.'}, 'createdBy': {'$ref': '#/components/schemas/Actor'}, 'updatedBy': {'$ref': '#/components/schemas/Actor'}}, 'additionalProperties': False, 'required': ['cursor', 'agent_id', 'scopes', 'rev', 'createdBy', 'updatedBy']}, 'Counts': {'type': 'object', 'properties': {'cards': {'type': 'integer', 'minimum': 0, 'maximum': 9007199254740991}, 'people': {'type': 'integer', 'minimum': 0, 'maximum': 9007199254740991}, 'projects': {'type': 'integer', 'minimum': 0, 'maximum': 9007199254740991}, 'proposals': {'type': 'integer', 'minimum': 0, 'maximum': 9007199254740991}, 'archives': {'type': 'integer', 'minimum': 0, 'maximum': 9007199254740991}}, 'additionalProperties': False, 'required': ['cards', 'people', 'projects', 'proposals', 'archives']}, 'ImportRequest': {'oneOf': [{'type': 'object', 'properties': {'mode': {'type': 'string', 'enum': ['validate']}, 'files': {'$ref': '#/components/schemas/FileMap'}}, 'additionalProperties': False, 'required': ['mode', 'files']}, {'type': 'object', 'properties': {'mode': {'type': 'string', 'enum': ['apply']}, 'files': {'$ref': '#/components/schemas/FileMap'}, 'hash': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}}, 'additionalProperties': False, 'required': ['mode', 'files', 'hash']}]}, 'ImportPreview': {'type': 'object', 'properties': {'hash': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}, 'counts': {'$ref': '#/components/schemas/Counts'}, 'warnings': {'type': 'array', 'items': {'type': 'string'}}}, 'additionalProperties': False, 'required': ['hash', 'counts', 'warnings']}, 'ImportApplied': {'type': 'object', 'properties': {'cursor': {'type': 'string', 'minLength': 1, 'description': 'Opaque board/epoch/commit-ordered sequence cursor.'}, 'counts': {'$ref': '#/components/schemas/Counts'}}, 'additionalProperties': False, 'required': ['cursor', 'counts']}, 'ImportResult': {'oneOf': [{'$ref': '#/components/schemas/ImportPreview'}, {'$ref': '#/components/schemas/ImportApplied'}]}, 'Export': {'type': 'object', 'properties': {'schema': {'type': 'integer', 'enum': [4]}, 'files': {'$ref': '#/components/schemas/FileMap'}, 'cursor': {'type': 'string', 'minLength': 1, 'description': 'Opaque board/epoch/commit-ordered sequence cursor.'}}, 'additionalProperties': False, 'required': ['schema', 'files', 'cursor']}, 'ErrorCode': {'type': 'string', 'enum': ['malformed_request', 'invalid_cursor', 'invalid_path', 'invalid_credential', 'forbidden', 'insufficient_scope', 'invalid_fence', 'attended_forbidden', 'actor_forbidden', 'personal_memory_forbidden', 'not_found', 'ineligible', 'capacity_exceeded', 'quota_exceeded', 'duplicate', 'import_nonempty', 'idempotency_conflict', 'preview_mismatch', 'dispatcher_conflict', 'capacity_below_occupancy', 'capability_unavailable', 'snapshot_required', 'revision_conflict', 'payload_too_large', 'invalid_schema', 'invalid_reference', 'dependency_cycle', 'unsafe_integer', 'protected_field', 'precondition_required', 'lock_retry']}, 'Error': {'type': 'object', 'properties': {'error': {'type': 'object', 'properties': {'code': {'$ref': '#/components/schemas/ErrorCode'}, 'message': {'type': 'string'}, 'request_id': {'type': 'string', 'minLength': 1}, 'paths': {'type': 'array', 'items': {'type': 'string'}}, 'retryable': {'type': 'boolean'}}, 'additionalProperties': False, 'required': ['code', 'message', 'request_id', 'retryable']}}, 'additionalProperties': False, 'required': ['error']}, 'Event': {'type': 'object', 'additionalProperties': False, 'properties': {'id': {'type': 'string'}, 'seq': {'$ref': '#/components/schemas/Bigint'}, 'actor': {'$ref': '#/components/schemas/Actor'}, 'principal': {'type': 'string'}, 'command': {'type': 'string'}, 'at': {'type': 'string'}, 'delta': {'type': 'object', 'additionalProperties': {}}, 'on_behalf_of': {'type': 'string', 'pattern': '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'}}, 'required': ['id', 'seq', 'actor', 'principal', 'command', 'at', 'delta'], 'description': 'Internal audit contract, not a standalone HTTP event endpoint. on_behalf_of is verified dispatcher assignee for display/audit only, grants nothing.'}}

def validate(value, schema):
    if value is None and schema.get('nullable'):
        return
    if '$ref' in schema:
        return validate(value, SCHEMAS[schema['$ref'].split('/')[-1]])
    if 'oneOf' in schema or 'anyOf' in schema:
        for variant in schema.get('oneOf', schema.get('anyOf', [])):
            try:
                validate(value, variant)
                return
            except AssertionError:
                pass
        raise AssertionError('no contract variant matches: ' + repr(value))
    types = schema.get('type')
    if types:
        checks = {'object': isinstance(value, dict), 'array': isinstance(value, list), 'string': isinstance(value, str),
                  'integer': isinstance(value, int) and not isinstance(value, bool), 'boolean': isinstance(value, bool), 'null': value is None,
                  'number': isinstance(value, (int, float)) and not isinstance(value, bool)}
        assert any(checks[t] for t in (types if isinstance(types, list) else [types])), repr(value)
    if 'enum' in schema:
        assert value in schema['enum'], repr(value)
    if isinstance(value, dict):
        assert all(k in value for k in schema.get('required', [])), repr(value)
        props = schema.get('properties', {})
        if schema.get('additionalProperties') is False:
            assert not set(value) - set(props), repr(set(value) - set(props))
        for key, child in value.items():
            rule = props.get(key, schema.get('additionalProperties', {}))
            if isinstance(rule, dict):
                validate(child, rule)
    if isinstance(value, list):
        for child in value:
            validate(child, schema.get('items', {}))
    if isinstance(value, str) and schema.get('pattern'):
        import re
        assert re.search(schema['pattern'], value), repr(value)


class MockBoard(http.server.ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self):
        super().__init__(('127.0.0.1', 0), Handler)
        self.files = copy.deepcopy(FIXTURE_FILES)
        self.revs = {p: 'rev-' + p + '-1' for p in self.files}
        self.version = 1
        self.calls, self.receipts, self.claims = [], {}, {}
        self.schemas_errors = []
        self.omit = False
        self.hydration_race = False
        self.conflict = False
        self.drop_response = False
        self.retry_lock = False
        self.deny_approve = False
        self.redirect = False
        self.identity = {**ACTOR, 'boards': [{'id': BOARD_ID, 'role': 'editor', 'handle': 'synthetic-a'}], 'token_scopes': ['read', 'write', 'claim']}
        self.thread = threading.Thread(target=self.serve_forever, daemon=True); self.thread.start()

    @property
    def api(self):
        return 'http://127.0.0.1:' + str(self.server_port)

    def close(self):
        self.shutdown(); self.server_close(); self.thread.join()

    def file(self, path):
        return {'path': path, 'body': copy.deepcopy(self.files[path]), 'rev': self.revs[path], 'createdBy': ACTOR, 'updatedBy': ACTOR}

    def snapshot(self):
        entities = []
        kinds = {'cards': 'card', 'people': 'person', 'projects': 'project', 'proposals': 'proposal'}
        for path in sorted(self.files):
            if path.split('/')[0] in kinds and not self.files[path].get('_archived'):
                value = self.file(path); value.pop('path'); value['kind'] = kinds[path.split('/')[0]]
                if self.omit and path.startswith('cards/'):
                    value['omitted'] = ['history', 'comments']; value['body'].pop('history', None); value['body'].pop('comments', None)
                entities.append(value)
        root = self.file('tasks.json'); root.pop('path')
        return {'schema': 4, 'board_id': BOARD_ID, 'root': root, 'entities': entities, 'cursor': 'cursor-' + str(self.version),
                'claims': list(self.claims.values()), 'capabilities': {'casWrites': True, 'atomicMultiFile': True, 'changeFeed': True,
                'phase': '0', 'lazyHistory': self.omit, 'teamDocuments': True, 'commands': ['create-card', 'claim', 'heartbeat', 'release', 'move', 'done', 'review', 'archive', 'unarchive', 'approve', 'comment']}}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, value, status=200, headers=None):
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json'); self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers(); self.wfile.write(raw)

    def error(self, code, status):
        self.send({'error': {'code': code, 'message': 'Synthetic refusal', 'request_id': 'synthetic', 'retryable': code == 'lock_retry'}}, status)

    def do_GET(self):
        s = self.server
        # The sandbox's port broker probes new listeners with an unauthenticated GET /.
        if self.path == '/' and not self.headers.get('Authorization'):
            return self.send({'status': 'synthetic-listener'})
        s.calls.append(('GET', self.path, None, dict(self.headers)))
        if s.redirect:
            return self.send({}, 302, {'Location': 'https://api.github.com/leak'})
        if self.path == '/v1/me':
            return self.send(s.identity)
        suffix = self.path.split('/v1/boards/' + BOARD_ID, 1)[-1]
        if suffix == '/snapshot':
            value = s.snapshot(); validate(value, SCHEMAS['Snapshot']); return self.send(value)
        if suffix.startswith('/files/'):
            path = urllib.parse.unquote(suffix[len('/files/'):])
            if path not in s.files:
                return self.error('not_found', 404)
            value = s.file(path)
            if s.hydration_race and path.startswith('cards/'):
                s.hydration_race = False; value['rev'] += '-raced'
            return self.send(value)
        if suffix.startswith('/changes?'):
            return self.send({'through': 'cursor-' + str(s.version), 'has_more': False, 'batches': []})
        return self.error('not_found', 404)

    def do_POST(self):
        s = self.server
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        s.calls.append(('POST', self.path, copy.deepcopy(body), dict(self.headers)))
        key = self.headers.get('Idempotency-Key')
        try:
            import uuid
            uuid.UUID(key)
            validate(body, SCHEMAS['CommitRequest' if self.path.endswith('/commits') else 'Command'])
        except (AssertionError, ValueError, TypeError) as e:
            s.schemas_errors.append(str(e)); return self.error('invalid_schema', 422)
        fingerprint = json.dumps(body, sort_keys=True)
        if key in s.receipts:
            old, response = s.receipts[key]
            if old != fingerprint:
                return self.error('idempotency_conflict', 409)
            return self.send(response)
        if s.retry_lock:
            s.retry_lock = False; return self.error('lock_retry', 503)
        if s.conflict:
            s.conflict = False
            s.files['cards/t_sample.json']['details'] = 'Concurrent synthetic detail'
            s.revs['cards/t_sample.json'] += '-concurrent'
            return self.error('revision_conflict', 412)
        paths = []
        if self.path.endswith('/commits'):
            for op in body['ops']:
                if op['baseRev'] != s.revs.get(op['path']):
                    return self.error('revision_conflict', 412)
                old = s.files[op['path']]
                if op['body'].get('history') != old.get('history'):
                    return self.error('actor_forbidden', 422)
                s.files[op['path']] = copy.deepcopy(op['body']); paths.append(op['path'])
            result = None
        else:
            kind = body['kind']; cid = body.get('card_id', body.get('entity_id')); path = 'cards/' + str(cid) + '.json'
            if kind != 'create-card' and body['baseRev'] != s.revs.get(path):
                return self.error('revision_conflict', 412)
            if kind == 'approve' and s.deny_approve:
                return self.error('insufficient_scope', 403)
            if kind == 'create-card':
                card = copy.deepcopy(body['card']); card['num'] = s.files['tasks.json']['next_num']
                s.files['tasks.json']['next_num'] += 1; path = 'cards/' + card['id'] + '.json'; s.files[path] = card
                result = {'card_id': card['id'], 'num': card['num']}; paths.append('tasks.json')
            else:
                card = s.files[path]
                if kind == 'claim':
                    s.proof_digest = body['proof_digest']
                    s.claims[cid] = {'card_id': cid, 'actor': ACTOR, 'session_id': body['session_id'], 'fence': '7', 'attended': False,
                                     'status': 'running', 'expires_at': '2099-01-02T03:34:05Z', 'live': True}
                    card['column'] = 'in-progress'; result = {'fence': '7', 'expires_at': '2099-01-02T03:34:05Z'}
                elif kind in ('heartbeat', 'release'):
                    if hashlib.sha256(bytes.fromhex(body['proof'])).hexdigest() != s.proof_digest:
                        return self.error('invalid_fence', 403)
                    result = {'fence': '7', 'expires_at': '2099-01-02T03:34:05Z'}
                    if kind == 'release':
                        s.claims.pop(cid, None); card['column'] = body.get('column', 'todo')
                        result = {'card_id': cid, 'column': card['column'], 'claim_ended': True}
                elif kind == 'comment':
                    card.setdefault('comments', []).append({'id': 'c_mock', 'text': body['text'], 'by': 'synthetic-a', 'actor': ACTOR, 'at': '2026-01-02T03:04:05Z'})
                    result = {'comment_id': 'c_mock', 'actor': ACTOR, 'at': '2026-01-02T03:04:05Z'}
                elif kind in ('archive', 'unarchive'):
                    year = body['year']; archive_path = 'archive/' + year + '.json'
                    if body['rootRev'] != s.revs['tasks.json'] or body['archiveRev'] != s.revs.get(archive_path):
                        return self.error('revision_conflict', 412)
                    archive = s.files.setdefault(archive_path, {'version': 3, 'archive': True, 'year': year, 'tasks': [], 'contacts': [], 'history': {}})
                    if kind == 'archive':
                        archive['tasks'].append(copy.deepcopy(card)); card['_archived'] = True
                        s.files['tasks.json'].setdefault('archive', {}).setdefault('files', {})[year] = {'tasks': len(archive['tasks']), 'contacts': 0}
                    else:
                        archive['tasks'] = [x for x in archive['tasks'] if x['id'] != cid]; card.pop('_archived', None); card['column'] = 'backlog'
                    paths += [archive_path, 'tasks.json']; result = {'entity_id': cid, 'year': year, 'archived': kind == 'archive'}
                else:
                    card['column'] = body.get('column', {'done': 'done', 'review': 'pending-review', 'approve': 'todo'}.get(kind, card['column']))
                    result = {'card_id': cid, 'column': card['column'], 'claim_ended': kind in ('done', 'review')}
            paths.append(path)
        s.version += 1
        for path in paths:
            s.revs[path] = 'rev-' + path + '-' + str(s.version)
        response = {'cursor': 'cursor-' + str(s.version), 'files': [{'path': p, 'rev': s.revs[p]} for p in paths]}
        if result is not None:
            response['result'] = result
        s.receipts[key] = (fingerprint, response)
        if s.drop_response:
            s.drop_response = False; self.close_connection = True; return
        self.send(response)


class HostedCLITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hosted-cli-'); self.root = Path(self.temp.name)
        self.cwd = self.root / 'checkout'; self.cwd.mkdir(); self.state = self.root / 'state'
        self.token = self.root / 'token'; self.token.write_text('kt_synthetic.' + 'a' * 64); self.token.chmod(0o600)
        self.bin = self.root / 'bin'; self.bin.mkdir(); gh = self.bin / 'gh'
        gh.write_text('#!/bin/sh\necho forbidden >> "$HOSTED_GH_TRAP"\nexit 99\n'); gh.chmod(0o700)
        self.server = MockBoard(); self.addCleanup(self.server.close); self.addCleanup(self.temp.cleanup)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('BOARD_', 'GH_', 'GITHUB_'))}
        self.env.update(BOARD_BACKEND='hosted', BOARD_HOSTED_API=self.server.api, BOARD_ID=BOARD_ID, BOARD_TOKEN_FILE=str(self.token),
                        BOARD_USER='forged-user', BOARD_AGENT='forged-agent', BOARD_SESSION='synthetic-session',
                        XDG_STATE_HOME=str(self.state), PATH=str(self.bin) + os.pathsep + self.env.get('PATH', ''), HOSTED_GH_TRAP=str(self.root/'gh-called'))

    def run_cli(self, *args, code=0):
        p = subprocess.run([sys.executable, str(KIT), *args], cwd=self.cwd, env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, code, p.stdout + p.stderr)
        self.assertFalse((self.root/'gh-called').exists(), 'hosted invoked gh')
        self.assertEqual(self.server.schemas_errors, [])
        for _, path, _, headers in self.server.calls:
            self.assertTrue(path.startswith('/v1/'), repr((path, headers)))
            self.assertNotIn('github', path.lower())
        return p

    def claim(self):
        self.run_cli('claim', '#17')

    def test_list_show_filters_and_hydration(self):
        self.server.omit = True
        self.assertIn('Synthetic contract sample', self.run_cli('list', '--assignee', 'synthetic-a').stdout)
        out = self.run_cli('show', '#17').stdout
        self.assertIn('Invented comment', out); self.assertIn('x-sample', out)
        self.assertTrue(any('/files/cards%2Ft_sample.json' in c[1] for c in self.server.calls))

    def test_create_uses_server_number_backlog(self):
        out = self.run_cli('add', 'Synthetic new', '--assign', 'synthetic-a', '--todo', 'Check').stdout
        self.assertIn('#900000', out)
        body = [c[2] for c in self.server.calls if c[0] == 'POST'][0]
        self.assertNotIn('num', body['card']); self.assertEqual(body['card']['column'], 'backlog')

    def test_create_carries_links(self):   # kit v78: add --link on a hosted board
        self.run_cli('add', 'Synthetic linked', '--link', 'https://example.test/a', 'Doc A', '--link', 'https://example.test/b')
        body = [c[2] for c in self.server.calls if c[0] == 'POST'][0]
        self.assertEqual([{'url': 'https://example.test/a', 'title': 'Doc A'}, {'url': 'https://example.test/b', 'title': 'https://example.test/b'}],
                         body['card']['links'])

    def test_create_stores_the_checked_labels(self):   # kit v81: a trailing break passes the check only once stripped
        self.run_cli('add', 'Synthetic labelled', '--label', 'ops\x85', '--label', ' ops', '--label', 'web')
        body = [c[2] for c in self.server.calls if c[0] == 'POST'][0]
        self.assertEqual(['ops', 'web'], body['card']['labels'])

    def test_create_refuses_a_reserved_client(self):   # kit v89: the hosted add runs the same check as every save
        for name in ('__proto__', ' constructor '):
            p = self.run_cli('add', 'Synthetic reserved', '--client', name, code=1)
            self.assertIn('cannot be a client or company name', p.stderr)
        self.assertEqual([], [c for c in self.server.calls if c[0] == 'POST'])

    def test_create_refuses_a_reserved_client_copied_from_its_project(self):   # kit v89 review: as the local add --project
        self.server.files['projects/pr_sample.json']['client'] = '__proto__'
        p = self.run_cli('add', 'Synthetic project card', '--project', 'pr_sample', code=1)
        self.assertIn('cannot be a client or company name', p.stderr); self.assertIn('project Synthetic Project', p.stderr)
        self.assertEqual([], [c for c in self.server.calls if c[0] == 'POST'])
        self.run_cli('add', 'Synthetic own client', '--project', 'pr_sample', '--client', 'Example Company')   # its own client copies nothing

    def test_unarchive_refuses_a_reserved_client(self):   # kit v89 review: the server restores it, so the CLI checks it first
        self.server.files['archive/2025.json']['tasks'][0]['client'] = '__proto__'
        p = self.run_cli('unarchive', '#2', code=1)
        self.assertIn('cannot be a client or company name', p.stderr)
        self.assertEqual([], [c for c in self.server.calls if c[0] == 'POST'])

    def test_unarchive_can_replace_a_reserved_client(self):   # kit v89 review round 2: hosted has no client-rename
        self.claim(); self.run_cli('move', '#17', 'backlog'); self.run_cli('archive', '#17')
        path = [p for p, f in self.server.files.items() if p.startswith('archive/') and any(x['id'] == 't_sample' for x in f['tasks'])][0]
        for card in [x for x in self.server.files[path]['tasks'] if x['id'] == 't_sample'] + [self.server.files['cards/t_sample.json']]:
            card['client'] = '__proto__'   # an old board archived it with a reserved client
        posts = len([c for c in self.server.calls if c[0] == 'POST'])
        p = self.run_cli('unarchive', '#17', code=1)
        self.assertIn("unarchive '#17' --client NEW", p.stderr); self.assertNotIn('client-rename', p.stderr)
        self.assertEqual(posts, len([c for c in self.server.calls if c[0] == 'POST']), 'nothing was posted')
        p = self.run_cli('unarchive', '#17', '--client', 'Proto Ltd', code=1)   # an agent could not save the new client after it
        self.assertIn('a person runs unarchive --client', p.stderr)
        self.assertEqual(posts, len([c for c in self.server.calls if c[0] == 'POST']), 'nothing was restored')
        self.server.identity['agent_id'] = None   # a person
        self.run_cli('unarchive', '#17', '--client', 'Proto Ltd')
        self.assertEqual('Proto Ltd', self.server.files['cards/t_sample.json']['client'], 'saved right after the restore')
        self.assertIn('Proto Ltd', self.server.files['tasks.json']['clients'])

    def test_legacy_board_api_still_works_with_a_note(self):   # kit v81: BOARD_HOSTED_API is the hosted URL now
        self.env['BOARD_API'] = self.env.pop('BOARD_HOSTED_API')
        p = self.run_cli('list', '--assignee', 'synthetic-a')
        self.assertIn('Synthetic contract sample', p.stdout); self.assertIn('BOARD_HOSTED_API', p.stderr)

    def test_holder_proofs_and_phase0_mutations(self):
        self.claim()
        proofs = list(self.state.rglob('*.json')); self.assertEqual(len(proofs), 1)
        self.assertEqual(proofs[0].stat().st_mode & 0o777, 0o600)
        self.assertFalse(list(self.cwd.rglob('*.json')))
        for args in [('heartbeat', '#17'), ('assign', '#17', 'synthetic-a'), ('link', '#17', 'https://example.test/doc'),
                     ('todo-add', '#17', 'Extra'), ('todo-done', '#17', '1'), ('todo-edit', '#17', '1', 'Updated'),
                     ('task-set', '#17', '--title', 'Reworded'), ('comment', '#17', 'Synthetic comment')]:
            self.run_cli(*args)
        mutations = [c for c in self.server.calls if c[0] == 'POST']
        self.assertTrue(all(c[3].get('Idempotency-Key') for c in mutations))
        self.assertEqual(self.server.files['cards/t_sample.json']['title'], 'Reworded')
        commit = next(c[2] for c in mutations if c[1].endswith('/commits'))
        self.assertEqual(commit['fences']['t_sample']['fence'], '7')
        self.run_cli('release', '#17'); self.assertFalse(list(self.state.rglob('*.json')))

    def test_412_field_merge_and_hydrated_history(self):
        self.claim(); self.server.omit = True; self.server.conflict = True
        original = copy.deepcopy(self.server.files['cards/t_sample.json']['history'])
        self.run_cli('task-set', '#17', '--title', 'My title')
        card = self.server.files['cards/t_sample.json']
        self.assertEqual(card['details'], 'Concurrent synthetic detail'); self.assertEqual(card['history'], original)
        posts = [c for c in self.server.calls if c[1].endswith('/commits')]
        self.assertEqual(len(posts), 2); self.assertNotEqual(posts[0][3]['Idempotency-Key'], posts[1][3]['Idempotency-Key'])

    def test_idempotency_replay_after_lost_response(self):
        self.server.drop_response = True
        self.run_cli('comment', '#17', 'Once')
        posts = [c for c in self.server.calls if c[0] == 'POST']
        self.assertEqual(len(posts), 2); self.assertEqual(posts[0][3]['Idempotency-Key'], posts[1][3]['Idempotency-Key'])
        self.assertEqual(sum(c['text'] == 'Once' for c in self.server.files['cards/t_sample.json']['comments']), 1)

    def test_approve_403_without_scope_and_no_fallback(self):
        self.server.deny_approve = True
        p = self.run_cli('approve', '#17', code=1)
        self.assertIn('insufficient_scope', p.stderr)
        self.assertEqual(self.server.files['cards/t_sample.json']['column'], 'backlog')

    def test_lifecycle_412_reloads_without_repeating(self):
        self.server.conflict = True
        p = self.run_cli('approve', '#17', code=3)
        self.assertIn('board reloaded', p.stderr)
        self.assertEqual(len([c for c in self.server.calls if c[0] == 'POST']), 1)

    def test_lifecycle_archive_unarchive(self):
        self.claim()
        self.run_cli('move', '#17', 'backlog')
        self.run_cli('archive', '#17')
        self.run_cli('unarchive', '#17')
        self.assertEqual(self.server.files['cards/t_sample.json']['column'], 'backlog')
        self.claim()
        self.run_cli('review', '#17', '--note', 'Synthetic review')
        self.claim()
        self.run_cli('done', '#17', '--note', 'Synthetic result')

    def test_hydration_race_reloads_before_replacement(self):
        self.claim(); self.server.omit = True; self.server.hydration_race = True
        self.run_cli('task-set', '#17', '--title', 'After hydration race')
        self.assertEqual(self.server.files['cards/t_sample.json']['title'], 'After hydration race')
        self.assertGreaterEqual(sum(c[1].endswith('/snapshot') for c in self.server.calls), 3)

    def test_retryable_lock_reuses_same_key(self):
        self.server.retry_lock = True
        self.run_cli('comment', '#17', 'Lock retry once')
        posts = [c for c in self.server.calls if c[0] == 'POST']
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0][3]['Idempotency-Key'], posts[1][3]['Idempotency-Key'])

    def test_docs_home_read_and_agent_setting_refusal_do_not_fall_back(self):
        from unittest.mock import patch
        home = {"provider": "google-drive", "root": "https://drive.google.com/drive/folders/synthetic-root"}
        self.server.files['tasks.json']['settings']['docs_home'] = home
        self.assertEqual(json.loads(self.run_cli('settings', '--json').stdout)['docs_home'], home)
        original = Handler.do_POST
        def owner_only(handler):
            if handler.path.endswith('/commits'):
                handler.server.calls.append(('POST', handler.path, None, dict(handler.headers)))
                return handler.error('invalid_fence', 403)
            return original(handler)
        with patch.object(Handler, 'do_POST', owner_only):
            result = self.run_cli('settings-set', '--docs-provider', 'local', '--docs-root', '/work/keeptrack', code=1)
        self.assertIn('invalid_fence', result.stderr)
        self.assertEqual(self.server.files['tasks.json']['settings']['docs_home'], home)
        self.assertEqual(len([c for c in self.server.calls if c[0] == 'POST']), 1)

    def test_hosted_docs_home_cannot_smuggle_legacy_settings(self):
        before = copy.deepcopy(self.server.files)
        for flags in [('--rename-stage', 'New=Changed'), ('--title', 'Changed'), ('--min-kit', '103'), ('--stages', 'New,Won')]:
            result = self.run_cli('settings-set', '--docs-provider', 'local', '--docs-root', '/docs/root', *flags, code=1)
            self.assertIn('docs-home-only', result.stderr)
        self.assertEqual(self.server.files, before)
        self.assertFalse(any(c[0] == 'POST' for c in self.server.calls))

    def test_agent_attended_claim_is_refused(self):
        p = self.run_cli('claim', '#17', '--attended', code=1)
        self.assertIn('attended_forbidden', p.stderr)
        self.assertFalse(any(c[0] == 'POST' for c in self.server.calls))

    def test_missing_or_exposed_proof_fails_closed(self):
        p = self.run_cli('link', '#17', 'https://example.test/synthetic', code=1)
        self.assertIn('invalid_fence', p.stderr)
        self.claim()
        proof = next(self.state.rglob('*.json')); proof.chmod(0o644)
        p = self.run_cli('heartbeat', '#17', code=1)
        self.assertIn('mode 0600', p.stderr)

    def test_live_authority_is_separate_from_imported_claim(self):
        self.server.files['cards/t_sample.json']['claim'] = {'agent': 'imported', 'status': 'running', 'session_id': 'inert', 'claimed_at': '2099-01-01T00:00:00Z'}
        out = self.run_cli('list', '--unclaimed').stdout
        self.assertIn('Synthetic contract sample', out)
        self.assertNotIn('imported:running', out)
        self.claim()
        out = self.run_cli('list', '--unclaimed').stdout
        self.assertNotIn('Synthetic contract sample', out)

    def test_load_save_seam_uses_captured_revision(self):
        self.claim()
        script = ("import runpy,sys; k=runpy.run_path(sys.argv[1]); "
                  "data,state=k['load'](); data['tasks'][0]['title']='Saved through seam'; "
                  "print(k['save_changes'](data,state))")
        result = subprocess.run([sys.executable, '-c', script, str(KIT)], cwd=self.cwd, env=self.env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('True', result.stdout)
        self.assertEqual(self.server.files['cards/t_sample.json']['title'], 'Saved through seam')
        self.server.conflict = True
        result = subprocess.run([sys.executable, '-c', script.replace('Saved through seam', 'Stale seam write'), str(KIT)],
                                cwd=self.cwd, env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('False', result.stdout)
        self.assertEqual(self.server.files['cards/t_sample.json']['title'], 'Saved through seam')
        self.assertEqual(self.server.schemas_errors, [])
        self.assertFalse((self.root/'gh-called').exists())

    def test_unsupported_command_fails_before_http(self):
        p = self.run_cli('proposals', code=1)
        self.assertIn('capability_unavailable', p.stderr); self.assertEqual(self.server.calls, [])

    def test_credential_is_never_forwarded_to_github(self):
        for api in ('https://api.github.com', 'https://gist.github.com', 'https://rain-ventures-ai.github.io'):
            self.env['BOARD_HOSTED_API'] = api
            p = self.run_cli('list', code=1); self.assertIn('never a GitHub host', p.stderr)
            self.assertEqual(self.server.calls, [])
        self.env['BOARD_HOSTED_API'] = self.server.api; self.server.redirect = True
        self.run_cli('list', code=1)
        self.assertEqual(len(self.server.calls), 1)

    def test_file_mode_overrides_backend(self):
        board = self.cwd / 'tasks.json'
        board.write_text(json.dumps({'version': 3, 'tasks': [], 'contacts': [], 'people': [], 'columns': [], 'settings': {}}))
        self.run_cli('--file', str(board), 'list'); self.assertEqual(self.server.calls, [])


if __name__ == '__main__':
    unittest.main()
