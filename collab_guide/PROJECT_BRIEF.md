# Collaborative Workspace System - Implementation Brief

## Project Overview

Build a self-hosted, live collaborative workspace system (like Google Docs but for entire folder structures) that supports:
- Real-time folder tree synchronization across multiple clients
- Google Docs-style collaborative file editing (multi-writer with CRDT)
- VS Code extension as primary client interface
- AI agent as first-class client that can edit files on schedule
- Server is canonical source of truth with persistence

## Full Design Document

**CRITICAL:** Read the complete engineering design first: `docs/collaborative-workspace-design.md`

This document contains:
- Full architecture diagrams
- WebSocket protocol message schemas
- Persistence strategy
- Yjs integration details
- VS Code extension design
- AI agent design
- Three-phase roadmap (Phase 0, 1, 2)

## What to Build (Phase 0 - MVP)

We're implementing Phase 0 first: a minimal working system that proves the architecture.

### Phase 0 Scope
- Single workspace (hardcoded workspace ID for now)
- Token-based auth (single admin token, no DB yet)
- Folder tree: read-only from server (server reads from disk)
- File read: clients can open and view files
- File write: single-writer lock (first client to open gets write lock)
- Persistence: files on disk, metadata in JSON files
- WebSocket server with basic protocol
- VS Code extension: TreeView + file viewer/editor

### What NOT to Build Yet (Phase 1 & 2)
- ❌ Multi-user concurrent editing (Yjs) - Phase 2
- ❌ Folder operations from client (create, rename, delete) - Phase 1
- ❌ User accounts and permissions - Phase 1
- ❌ PostgreSQL database - Phase 1
- ❌ AI agent - Phase 2
- ❌ Presence/cursors - Phase 2

## Tech Stack (Phase 0)

### Server
- **Runtime:** Node.js 20+ with TypeScript
- **WebSocket:** `ws` library
- **Storage:** Local filesystem (organized by workspace)
- **Auth:** Simple token validation (env var)
- **No Database Yet:** Use JSON files for metadata

### VS Code Extension
- **Language:** TypeScript
- **Key APIs:**
  - `TreeDataProvider` - Display remote folder tree
  - `FileSystemProvider` - Handle remote file open/read/write
  - WebSocket client to connect to server

## Directory Structure to Create

```
collab-server/
├── src/
│   ├── protocol/
│   │   ├── messages.ts          # Message type definitions
│   │   ├── handlers.ts          # Message handler dispatch
│   │   └── validation.ts        # Message validation
│   ├── storage/
│   │   ├── fileStorage.ts       # Read/write workspace files
│   │   └── treeState.ts         # Folder tree JSON management
│   ├── collab/
│   │   ├── sessionManager.ts    # Active WebSocket sessions
│   │   ├── workspaceManager.ts  # Workspace state
│   │   └── broadcaster.ts       # Send messages to clients
│   ├── auth/
│   │   └── tokenValidator.ts    # Validate auth tokens
│   ├── server.ts                # WebSocket server entry point
│   └── types.ts                 # Shared TypeScript types
├── storage/                      # Not in git (runtime data)
│   └── workspaces/
│       └── ws_default/           # Default workspace
│           ├── files/            # Actual files
│           └── tree.json         # Folder structure metadata
├── package.json
├── tsconfig.json
└── .env

vscode-extension/
├── src/
│   ├── extension.ts             # Extension entry point
│   ├── connection/
│   │   ├── websocket.ts         # WebSocket client
│   │   └── messageHandler.ts   # Handle server messages
│   ├── auth/
│   │   └── tokenManager.ts      # Store/retrieve token
│   ├── tree/
│   │   └── treeProvider.ts      # TreeDataProvider implementation
│   ├── fs/
│   │   ├── remoteFS.ts          # FileSystemProvider implementation
│   │   └── fileCache.ts         # Local cache for performance
│   └── types.ts                 # Shared TypeScript types
├── package.json
└── tsconfig.json
```

## WebSocket Protocol (Phase 0 Messages)

### Client → Server

**JOIN** - Connect to workspace
```json
{
  "type": "JOIN",
  "payload": {
    "workspaceId": "ws_default",
    "token": "dev-admin-token-12345"
  }
}
```

**OPEN_FILE** - Request to open/lock file
```json
{
  "type": "OPEN_FILE",
  "payload": {
    "docId": "/src/main.ts"
  }
}
```

**CLOSE_FILE** - Close file and release lock
```json
{
  "type": "CLOSE_FILE",
  "payload": {
    "docId": "/src/main.ts"
  }
}
```

**FILE_UPDATE** - Send file changes (simple text replacement for Phase 0)
```json
{
  "type": "FILE_UPDATE",
  "payload": {
    "docId": "/src/main.ts",
    "content": "new file content here"
  }
}
```

### Server → Client

**JOINED** - Successful connection
```json
{
  "type": "JOINED",
  "payload": {
    "sessionId": "sess_abc123",
    "workspaceId": "ws_default"
  }
}
```

**TREE_SNAPSHOT** - Full folder tree
```json
{
  "type": "TREE_SNAPSHOT",
  "payload": {
    "tree": {
      "type": "directory",
      "name": "root",
      "path": "/",
      "children": [
        {
          "type": "file",
          "name": "README.md",
          "path": "/README.md",
          "size": 1024,
          "mtime": "2026-02-05T17:30:00Z"
        }
      ]
    }
  }
}
```

**FILE_SNAPSHOT** - File contents after OPEN_FILE
```json
{
  "type": "FILE_SNAPSHOT",
  "payload": {
    "docId": "/src/main.ts",
    "content": "console.log('hello');",
    "locked": true,
    "lockedBy": "sess_abc123"
  }
}
```

**FILE_UPDATE** - Broadcast file changes to other clients
```json
{
  "type": "FILE_UPDATE",
  "payload": {
    "docId": "/src/main.ts",
    "content": "updated content",
    "sessionId": "sess_xyz789"
  }
}
```

**ERROR** - Error response
```json
{
  "type": "ERROR",
  "payload": {
    "code": "FILE_LOCKED",
    "message": "File is locked by another user",
    "details": { "lockedBy": "sess_xyz789" }
  }
}
```

## Key Implementation Details

### Server: File Locking (Phase 0)
- Track which session has lock on each file
- Map: `docId → sessionId`
- When client opens file: check if locked, grant lock if available
- When client closes file or disconnects: release lock
- Only locked session can send FILE_UPDATE

### Server: File Storage
- Workspace files stored at: `storage/workspaces/{workspaceId}/files/**`
- Tree metadata at: `storage/workspaces/{workspaceId}/tree.json`
- On startup: scan filesystem, build tree.json if missing
- On FILE_UPDATE: write to disk immediately (simple persistence)

### VS Code: Remote File Scheme
- Use custom URI scheme: `collab://ws_default/src/main.ts`
- FileSystemProvider intercepts all file operations
- When VS Code opens file: send OPEN_FILE to server
- When user edits: send FILE_UPDATE to server
- When server sends FILE_UPDATE: update VS Code editor if file is open

### VS Code: Tree View
- Custom view in Explorer sidebar
- Shows remote workspace folder structure
- Click file → opens with `collab://` URI
- Refresh button to reload tree from server

## Implementation Order

### Step 1: Server Foundation (Build This First)
1. `src/types.ts` - TypeScript interfaces for all message types
2. `src/protocol/messages.ts` - Message type definitions
3. `src/storage/fileStorage.ts` - Read/write files from disk
4. `src/storage/treeState.ts` - Build tree from filesystem
5. `src/collab/sessionManager.ts` - Track connected clients
6. `src/auth/tokenValidator.ts` - Simple token check
7. `src/server.ts` - WebSocket server, message routing

### Step 2: VS Code Extension
1. `src/types.ts` - Shared message types (copy from server)
2. `src/connection/websocket.ts` - WebSocket client
3. `src/tree/treeProvider.ts` - TreeDataProvider
4. `src/fs/remoteFS.ts` - FileSystemProvider
5. `src/extension.ts` - Wire everything together

### Step 3: Testing
1. Start server: `npm run dev`
2. Create test workspace: `storage/workspaces/ws_default/files/test.txt`
3. Run extension in VS Code (F5)
4. Connect to workspace
5. View folder tree
6. Open and edit files
7. Test with multiple VS Code windows (file locking)

## Success Criteria (Phase 0)

- ✅ Server starts and accepts WebSocket connections
- ✅ VS Code extension connects to server
- ✅ Folder tree appears in VS Code sidebar
- ✅ Can click file in tree → file opens in editor
- ✅ Can edit file → changes persist to disk on server
- ✅ Second client sees "file locked" when trying to edit locked file
- ✅ Server restart preserves all files (disk persistence)

## What You Need to Do

1. **Read the full design doc:** `docs/collaborative-workspace-design.md` (30 min)
2. **Implement server components** in order listed above
3. **Implement VS Code extension** components
4. **Test end-to-end** with the success criteria

## Key Constraints

- Keep it simple - Phase 0 is about proving the architecture
- No premature optimization - single node, no database yet
- File locking is simple: first come, first served
- No Yjs yet - plain text content only
- No folder operations from client yet (read-only tree)
- Hardcoded workspace ID "ws_default" is fine

## Questions to Ask Me

If you're unsure about:
- Message format or protocol details → Check design doc first
- Edge cases (e.g., what happens if client disconnects while holding lock?) → Use common sense: release lock on disconnect
- Performance concerns → Ignore for Phase 0, we'll optimize later
- Security concerns → Minimal for Phase 0 (single token), we'll add proper auth in Phase 1

## Next Phases (After Phase 0 Works)

- **Phase 1:** Multi-client tree sync, folder operations (create/delete/rename), PostgreSQL, user accounts
- **Phase 2:** Yjs collaborative editing, presence cursors, AI agent integration

But don't think about those yet. Focus on Phase 0 only.

---

## Quick Start Commands

```bash
# Server setup
cd collab-server
npm install
cp .env.example .env
mkdir -p storage/workspaces/ws_default/files
echo "Hello World" > storage/workspaces/ws_default/files/test.txt
npm run dev

# Extension setup (separate terminal)
cd vscode-extension
npm install
# Press F5 in VS Code to launch extension development host
```

## Priority: Get Something Working End-to-End

The goal is to see a file from the server appear in VS Code and be editable. Everything else is secondary.

Start with the minimal server that can:
1. Accept WebSocket connection
2. Send TREE_SNAPSHOT
3. Handle OPEN_FILE
4. Send FILE_SNAPSHOT
5. Handle FILE_UPDATE and persist to disk

Then minimal VS Code extension that can:
1. Connect to server
2. Show tree in sidebar
3. Open files with custom URI scheme
4. Send edits back to server

This will prove the entire architecture works before adding complexity.
