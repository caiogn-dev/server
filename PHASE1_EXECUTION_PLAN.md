# Phase 1 - Backend P0 (Critical) Execution Plan

## Issues Identified

### 1. Store vs CompanyProfile Competition
**Current State:**
- `apps.stores.models.Store` - Full business entity with address, phone, operating hours
- `apps.automation.models.CompanyProfile` - Has duplicate fields but links to Store
- CompanyProfile has properties that delegate to Store when available

**Solution:** 
- Keep Store as single source of truth
- CompanyProfile becomes AutomationProfile - only automation-specific settings
- Remove duplicate property definitions in CompanyProfile

### 2. Duplicate Handover Models
**Current State:**
- `apps.handover.models.ConversationHandover` - Full handover protocol
- `apps.conversations.models.ConversationHandover` - Simpler version
- Both have different field structures

**Solution:**
- Keep `apps.handover` as the canonical authority
- Remove duplicate from `apps.conversations`
- Update references

### 3. Duplicate Messenger Models
**Current State:**
- `apps.messenger.models` - Complete Messenger implementation
- `apps.messaging.models` - Has MessengerAccount, MessengerConversation, etc.

**Solution:**
- `apps.messaging` appears more complete (has webhook logs, extensions)
- Freeze `apps.messenger` (mark as deprecated)
- Keep `apps.messaging` as canonical

### 4. Duplicate Flow Models in apps.automation
**Current State:**
- `AgentFlow`, `FlowSession`, `FlowExecutionLog` in automation/models.py

**Solution:**
- These are POC models, keep them but mark clearly

### 5. company_id vs store_id in contracts
**Current State:**
- Many APIs use company_id parameter
- Should migrate to store_id

**Solution:**
- Update API views to accept store_id
- Maintain backward compatibility with company_id

## Execution Steps

1. Fix CompanyProfile - remove duplicate properties
2. Remove duplicate ConversationHandover from conversations
3. Mark apps.messenger as deprecated
4. Update API views for store_id support
5. Run migrations and tests
