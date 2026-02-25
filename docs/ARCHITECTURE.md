# Collaborative Workspace Architecture

**Created:** February 12, 2026

## Table of Contents
1. [System Overview](#system-overview)
2. [Server Architecture](#server-architecture)
3. [Extension Architecture](#extension-architecture)
4. [CREATE_FILE Flow](#create_file-flow)
5. [Test Points & Failure Scenarios](#test-points--failure-scenarios)

---

## System Overview

The collaborative workspace system enables real-time file synchronization between multiple VS Code instances through a WebSocket server hosted on Azure.

### High-Level Architecture

```
VS Code Client A                    Azure Server                    VS Code Client B
┌──────────────┐                  ┌──────────────┐                ┌──────────────┐
│ RemoteFS     │◄────WebSocket────►│  Protocol    │◄───WebSocket───►│ RemoteFS     │
│ LocalSync    │                  │  Handler     │                │ LocalSync    │
│ Connection   │                  │              │                │ Connection   │
└──────────────┘                  │  Session     │                └──────────────┘
                                  │  Manager     │
                                  │              │
                                  │  File        │
                                  │  Storage     │
                                  └──────────────┘
                                        │
                                   Disk Storage
                                   (files/)
```

### Key Principles

1. **Server as Source of Truth**: All file state lives on Azure
2. **Lock-Based Editing**: One writer per file at a time
3. **Optimistic Local Changes**: LocalSync detects and syncs changes
4. **Broadcast Updates**: Server broadcasts to all clients

---

## Server Architecture

Location: `collab-server/`

### Component Diagram

```
┌─────────────────────────────────────────────────┐
│              server.ts                          │
│  - HTTP Server                                  │
│  - WebSocketServer                              │
│  - Connection Management                        │
└───────────────────┬─────────────────────────────┘
                    │
        ┌───────────▼──────────────┐
        │   ProtocolHandler        │
        │   - Message routing      │
        │   - handleCreateFile()   │
        │   - handleOpenFile()     │
        │   - handleFileUpdate()   │
        └┬────────┬────────┬───────┘
         │        │        │
    ┌────▼────┐ ┌▼──────┐ ┌▼──────────┐
    │Session  │ │File   │ │Broad-     │
    │Manager  │ │Storage│ │caster     │
    │(Locks)  │ │(Disk) │ │(Messages) │
    └─────────┘ └───────┘ └───────────┘
```

### 1. Server Entry (`server.ts`)

**Responsibilities:**
- Create HTTP + WebSocket servers
- Handle WebSocket connections
- Route messages to ProtocolHandler

**Key Code:**
```typescript
class CollabServer {
  wss.on('connection', (ws) => {
    ws.on('message', (data) => {
      const sessionId = this.wsToSession.get(ws);
      this.protocolHandler.handleMessage(ws, data, sessionId);
    });
  });
}
```

### 2. Protocol Handler (`protocol/handlers.ts`)

**Message Routing:**
```typescript
async handleMessage(ws, data, sessionId) {
  const message = JSON.parse(data);

  switch (message.type) {
    case 'JOIN': await this.handleJoin(ws, message);
    case 'CREATE_FILE': await this.handleCreateFile(ws, message, sessionId);
    case 'OPEN_FILE': await this.handleOpenFile(ws, message, sessionId);
    case 'FILE_UPDATE': await this.handleFileUpdate(ws, message, sessionId);
    case 'CLOSE_FILE': await this.handleCloseFile(ws, message, sessionId);
  }
}
```

**Critical Handler: handleCreateFile()**
```typescript
async handleCreateFile(ws, message, sessionId) {
  // 1. Validate session
  const session = this.sessionManager.getSession(sessionId);

  // 2. Validate path (prevent ../../etc/passwd)
  PathValidator.validateDocId(docId);

  // 3. Check file doesn't exist
  const exists = await this.fileStorage.fileExists(workspaceId, docId);
  if (exists) return sendError('FILE_EXISTS');

  // 4. Create file (auto-creates directories)
  await this.fileStorage.writeFile(workspaceId, docId, content);

  // 5. Acquire lock for creator
  const locked = this.sessionManager.acquireLock(workspaceId, docId, sessionId);

  // 6. Send FILE_SNAPSHOT to creator
  this.broadcaster.send(ws, {
    type: 'FILE_SNAPSHOT',
    payload: { docId, content, locked, lockedBy: sessionId }
  });

  // 7. Broadcast TREE_SNAPSHOT to all clients
  const tree = await this.treeState.buildTree(workspaceRoot);
  this.broadcaster.broadcast(allClients, {
    type: 'TREE_SNAPSHOT',
    payload: { tree }
  });
}
```

### 3. Session Manager (`collab/sessionManager.ts`)

**Responsibilities:**
- Track active sessions
- Manage file locks

**Data Structure:**
```typescript
private sessions: Map<sessionId, Session>
private locks: Map<workspaceId, Map<docId, sessionId>>
```

**Key Methods:**
- `acquireLock(workspace, docId, session)` - Try to get lock
- `releaseLock(workspace, docId, session)` - Release lock
- `hasLock(workspace, docId, session)` - Check lock ownership

### 4. File Storage (`storage/fileStorage.ts`)

**Responsibilities:**
- Read/write files to disk
- Auto-create parent directories

**File Structure:**
```
storage/
└── workspaces/
    └── ws_default/
        └── files/
            ├── test.txt
            └── src/
                └── utils/
                    └── helper.ts
```

**Auto-Directory Creation:**
```typescript
async writeFile(workspaceId, docId, content) {
  const filePath = this.getFilePath(workspaceId, docId);

  // Create parent directories
  const dir = path.dirname(filePath);
  await fs.mkdir(dir, { recursive: true });

  await fs.writeFile(filePath, content, 'utf-8');
}
```

### 5. Broadcaster (`collab/broadcaster.ts`)

**Methods:**
- `send(ws, message)` - Send to one client
- `broadcast(clients[], message)` - Send to multiple
- `sendError(ws, code, message)` - Send error

---

## Extension Architecture

Location: `extensions/collab-workspace/`

### Component Diagram

```
┌─────────────────────────────────────────────┐
│           extension.ts                      │
│   - Activate extension                      │
│   - Register FileSystemProvider             │
│   - Register commands                       │
└────────┬──────────────┬─────────────────────┘
         │              │
    ┌────▼─────┐   ┌────▼─────────┐
    │RemoteFS  │   │LocalSync     │
    │Provider  │   │Manager       │
    └────┬─────┘   └────┬─────────┘
         │              │
         └──────┬───────┘
                │
        ┌───────▼────────┐
        │  Collab        │
        │  Connection    │
        │  (WebSocket)   │
        └────────────────┘
```

### 1. Extension Entry (`extension.ts`)

**Activation:**
```typescript
export function activate(context) {
  const connection = new CollabConnection(SERVER_URL);

  // Register FileSystemProvider for 'collab://' scheme
  const remoteFS = new RemoteFileSystemProvider(connection);
  context.subscriptions.push(
    vscode.workspace.registerFileSystemProvider('collab', remoteFS)
  );

  // Start local sync
  const localSync = new LocalSyncManager(connection, localRoot);
  await localSync.start();

  // Register commands
  vscode.commands.registerCommand('collab.connect', () => {
    connection.connect();
  });
}
```

### 2. WebSocket Connection (`connection/websocket.ts`)

**Outgoing Messages:**
```typescript
class CollabConnection extends EventEmitter {
  joinWorkspace(workspaceId: string)
  openFile(docId: string)
  createFile(docId: string, content?: string)
  updateFile(docId: string, content: string)
  closeFile(docId: string)
}
```

**Incoming Message Handling:**
```typescript
private handleMessage(data: string) {
  const message = JSON.parse(data);

  switch (message.type) {
    case 'FILE_SNAPSHOT':
      this.emit('fileSnapshot', message.payload);
    case 'TREE_SNAPSHOT':
      this.emit('treeSnapshot', message.payload);
    case 'ERROR':
      this.emit('error', message.payload);
  }
}
```

### 3. RemoteFS Provider (`fs/remoteFS.ts`)

**Implements VS Code FileSystemProvider interface:**
```typescript
class RemoteFileSystemProvider implements vscode.FileSystemProvider {
  stat(uri): FileStat
  readDirectory(uri): [string, FileType][]
  readFile(uri): Uint8Array
  writeFile(uri, content, options)
  delete(uri, options)
  rename(oldUri, newUri, options)
}
```

**File Creation Detection:**
```typescript
async writeFile(uri, content, options) {
  const path = this.uriToPath(uri);

  // Detect new file creation
  if (options.create && !this.fileCache.has(path)) {
    // NEW FILE - send CREATE_FILE
    return new Promise((resolve, reject) => {
      this.pendingSnapshots.set(path, { resolve, reject });
      this.connection.createFile(path, text);

      setTimeout(() => {
        if (this.pendingSnapshots.has(path)) {
          reject(new Error(`Timeout creating file: ${path}`));
        }
      }, 5000);
    });
  }

  // EXISTING FILE - check for lock
  if (!this.openFiles.has(path)) {
    throw vscode.FileSystemError.NoPermissions('File not opened');
  }

  this.connection.updateFile(path, text);
}
```

**State Management:**
```typescript
private fileCache: Map<path, content> = new Map();
private openFiles: Set<path> = new Set(); // Files we have locks on
private pendingSnapshots: Map<path, {resolve, reject}> = new Map();
```

### 4. LocalSync Manager (`sync/localSyncManager.ts`)

**Bidirectional Sync:**
```
Local Disk ↔ LocalSyncManager ↔ Server
  (C:\...)     (File Watcher)    (Azure)
```

**Change Detection:**
```typescript
async handleFileChange(uri) {
  const docId = this.uriToDocId(uri);
  const content = await fs.readFile(uri.fsPath, 'utf-8');
  const hash = await this.hashContent(content);

  // Check if content actually changed
  if (this.metadata.fileHashes[docId] === hash) {
    return; // No change
  }

  // Determine if new or existing
  const isNewFile = !(docId in this.metadata.fileHashes);

  // Update metadata
  this.metadata.fileHashes[docId] = hash;
  await this.saveMetadata();

  if (isNewFile) {
    console.log(`[LocalSync] NEW file, calling createFile: ${docId}`);
    this.connection.createFile(docId, content);
  } else {
    console.log(`[LocalSync] EXISTING file, calling openFile: ${docId}`);
    this.connection.openFile(docId);
    // Will upload after acquiring lock
  }
}
```

**Metadata Structure:**
```typescript
// Stored in: .collab-workspace/ws_default/.collab/sync-metadata.json
{
  "fileHashes": {
    "/test.txt": "sha256:abc123...",
    "/src/helper.ts": "sha256:def456..."
  }
}
```

**Preventing Sync Loops:**
```typescript
// Track change source
private lastChangeSource: Map<docId, 'local' | 'remote'> = new Map();

// When downloading from server
async handleFileSnapshot(payload) {
  await fs.writeFile(localPath, payload.content);
  this.lastChangeSource.set(docId, 'remote');

  // Update hash to prevent re-upload
  const hash = await this.hashContent(payload.content);
  this.metadata.fileHashes[docId] = hash;
}

// When file watcher fires
async handleFileChange(uri) {
  // Ignore if change came from remote
  if (this.lastChangeSource.get(docId) === 'remote') {
    this.lastChangeSource.delete(docId);
    return;
  }
  // ... proceed with upload
}
```

---

## CREATE_FILE Flow

### Complete Step-by-Step

**User Action:** Create `/src/utils/helper.ts` in VS Code

**Step 1: LocalSync Detection**
```
[LocalSync] File watcher event: /src/utils/helper.ts
[LocalSync] isNewFile = true (not in metadata)
[LocalSync] NEW file, calling createFile: /src/utils/helper.ts
```

**Step 2: Extension → Server**
```json
WebSocket Message:
{
  "type": "CREATE_FILE",
  "payload": {
    "docId": "/src/utils/helper.ts",
    "content": "// Helper utilities\n"
  }
}
```

**Step 3: Server Receives & Routes**
```typescript
[Protocol] Received message type: "CREATE_FILE"
[Protocol] ✅ HANDLER VERSION: CREATE_FILE_ENABLED_v3
→ Routes to handleCreateFile()
```

**Step 4: Server Validates & Creates**
```typescript
// Validate session exists ✓
// Validate path security ✓
// Check file doesn't exist ✓

// Create file (auto-creates src/utils/)
await fileStorage.writeFile('ws_default', '/src/utils/helper.ts', content);
→ Created: storage/workspaces/ws_default/files/src/utils/helper.ts

[Protocol] Created file: /src/utils/helper.ts in workspace ws_default
```

**Step 5: Server Acquires Lock**
```typescript
const locked = sessionManager.acquireLock('ws_default', docId, sessionId);
→ Lock acquired for creator
```

**Step 6: Server → Creator (FILE_SNAPSHOT)**
```json
{
  "type": "FILE_SNAPSHOT",
  "payload": {
    "docId": "/src/utils/helper.ts",
    "content": "// Helper utilities\n",
    "locked": true,
    "lockedBy": "session-abc-123"
  }
}
```

**Step 7: Server → All Clients (TREE_SNAPSHOT)**
```json
{
  "type": "TREE_SNAPSHOT",
  "payload": {
    "tree": [
      { "name": "src", "type": "directory", "path": "/src", "children": [
        { "name": "utils", "type": "directory", "path": "/src/utils", "children": [
          { "name": "helper.ts", "type": "file", "path": "/src/utils/helper.ts" }
        ]}
      ]}
    ]
  }
}
```

**Step 8: Creator Receives Confirmation**
```typescript
// RemoteFS resolves pending promise
this.pendingSnapshots.get(docId).resolve(buffer);
this.fileCache.set(docId, buffer);
→ VS Code marks file as saved (no longer dirty)
```

**Step 9: LocalSync Updates Metadata**
```typescript
this.metadata.fileHashes['/src/utils/helper.ts'] = hash;
await this.saveMetadata();
→ Prevents re-upload on next file watcher event
```

**Step 10: All Clients Update Tree**
```typescript
// All clients receive TREE_SNAPSHOT
this.rootTree = tree;
this._emitter.fire([{ type: Changed, uri: 'collab://ws_default/' }]);
→ VS Code Explorer refreshes, shows helper.ts for all users
```

### Flow Diagram

```
User creates file
       │
       ▼
LocalSync detects (isNewFile=true)
       │
       ▼
connection.createFile()
       │
       │ WebSocket: CREATE_FILE
       ▼
Server: ProtocolHandler
  1. Validate session ✓
  2. Validate path ✓
  3. Check doesn't exist ✓
  4. fileStorage.writeFile() → creates src/utils/helper.ts
  5. sessionManager.acquireLock() → creator gets lock
       │
       ├─────────────────┬─────────────────┐
       │                 │                 │
       ▼                 ▼                 ▼
  FILE_SNAPSHOT   TREE_SNAPSHOT   TREE_SNAPSHOT
  (to creator)    (to creator)    (to other clients)
       │                 │                 │
       ▼                 ▼                 ▼
   Creator          All clients     All clients
   - Cache file     - Update tree   - Update tree
   - Mark saved     - Show in       - Show in
   - Update           explorer        explorer
     metadata
```

---

## Test Points & Failure Scenarios

### Server Test Points

#### 1. CREATE_FILE Tests

**✓ Valid CREATE_FILE**
- Input: Valid docId, content, session joined
- Expected: File created, lock acquired, snapshots sent
- Assertions:
  - File exists on disk at correct path
  - Creator has lock
  - FILE_SNAPSHOT sent to creator
  - TREE_SNAPSHOT broadcast to all

**✗ CREATE_FILE for existing file**
- Input: docId that already exists
- Expected: Error response
- Assertions:
  - Error code = `FILE_EXISTS`
  - File content unchanged
  - No lock acquired

**✗ CREATE_FILE without session**
- Input: Client not joined
- Expected: Error response
- Assertions:
  - Error code = `NOT_JOINED`
  - No file created

**✗ CREATE_FILE with path traversal**
- Input: docId = `../../etc/passwd`
- Expected: Error response
- Assertions:
  - Error code = `INVALID_PATH`
  - No file created outside workspace

**✓ CREATE_FILE with nested directories**
- Input: docId = `/src/utils/helper.ts` (directories don't exist)
- Expected: Directories auto-created, file created
- Assertions:
  - File exists at path
  - Directories `src/` and `src/utils/` created
  - Tree reflects structure

**⚡ Concurrent CREATE_FILE**
- Input: Two clients create same file simultaneously
- Expected: One succeeds, one gets error
- Assertions:
  - Exactly one succeeds
  - One gets `FILE_EXISTS` error
  - File created once

#### 2. Session Manager Tests

**✓ Lock acquisition**
- Input: File unlocked
- Expected: Lock acquired
- Assertions:
  - `acquireLock()` returns true
  - `hasLock()` returns true

**✗ Lock contention**
- Input: File already locked by session A, session B tries
- Expected: Lock denied
- Assertions:
  - `acquireLock()` returns false
  - Session A still holds lock

**✓ Lock release**
- Input: Session holds lock, calls release
- Expected: Lock released
- Assertions:
  - Lock removed
  - Other sessions can now acquire

**⚡ Session disconnect**
- Input: Client disconnects while holding locks
- Expected: All locks released
- Assertions:
  - All locks for session removed
  - Other clients can acquire locks

#### 3. File Storage Tests

**✓ Write with auto-create directories**
- Input: Path with non-existent directories
- Expected: Directories created, file written
- Assertions:
  - File exists
  - Parent directories exist

**✓ File exists check - exists**
- Input: File exists on disk
- Expected: Returns true

**✓ File exists check - doesn't exist**
- Input: File doesn't exist
- Expected: Returns false

**✓ Read file**
- Input: File with content
- Expected: Returns content

### Extension Test Points

#### 1. RemoteFS Provider Tests

**✓ readFile - cached**
- Input: File in cache
- Expected: Returns immediately from cache
- Assertions:
  - No server request
  - Content matches cache

**✓ readFile - uncached**
- Input: File not in cache
- Expected: Requests from server
- Assertions:
  - OPEN_FILE sent
  - Waits for FILE_SNAPSHOT
  - Returns content after snapshot

**✓ writeFile - new file**
- Input: `options.create=true`, not in cache
- Expected: Sends CREATE_FILE
- Assertions:
  - CREATE_FILE message sent
  - Waits for FILE_SNAPSHOT
  - Cache updated after confirmation

**✗ writeFile - no lock**
- Input: File in cache, not in openFiles set
- Expected: Throws error
- Assertions:
  - Error = NoPermissions
  - No server request

**✓ writeFile - has lock**
- Input: File in openFiles set
- Expected: Sends FILE_UPDATE
- Assertions:
  - FILE_UPDATE sent
  - Cache updated

#### 2. LocalSync Manager Tests

**✓ Detect new file**
- Input: File not in metadata
- Expected: Calls createFile()
- Assertions:
  - `isNewFile = true`
  - CREATE_FILE sent
  - Metadata updated

**✓ Detect modified file**
- Input: File in metadata, hash changed
- Expected: Calls openFile()
- Assertions:
  - `isNewFile = false`
  - OPEN_FILE sent
  - After lock, FILE_UPDATE sent

**✓ Ignore unchanged file**
- Input: File watcher fires, hash unchanged
- Expected: No action
- Assertions:
  - No server requests
  - Metadata unchanged

**✓ Download server change**
- Input: FILE_SNAPSHOT from server
- Expected: Writes to local disk
- Assertions:
  - File written locally
  - Metadata updated
  - `lastChangeSource = 'remote'`

**✓ Prevent sync loop**
- Input: Download from server triggers file watcher
- Expected: Ignores change
- Assertions:
  - No re-upload
  - No infinite loop

### Critical Failure Scenarios

#### 1. Network Failures

**Timeout during CREATE_FILE**
- Symptom: No response from server
- Impact: File may or may not exist
- Mitigation: Timeout + retry, check fileExists

**WebSocket disconnection**
- Symptom: Connection lost
- Impact: Operations fail
- Mitigation: Reconnect logic, queue messages

#### 2. Server Failures

**Disk full**
- Symptom: writeFile() fails
- Impact: FILE_CREATE_ERROR
- Mitigation: Disk space monitoring

**Server crash after CREATE_FILE**
- Symptom: File created but no broadcast
- Impact: Clients out of sync
- Mitigation: Periodic REQUEST_FULL_SYNC

**Race condition**
- Symptom: Two clients create same file
- Impact: One gets error
- Mitigation: Proper error handling

#### 3. Extension Failures

**FILE_SNAPSHOT timeout**
- Symptom: No response within 5s
- Impact: Promise rejects
- Mitigation: Retry or show error

**Metadata corruption**
- Symptom: Invalid sync-metadata.json
- Impact: Can't determine new vs existing
- Mitigation: Reset metadata, rebuild

**Cache out of sync**
- Symptom: Stale cached content
- Impact: Wrong data displayed
- Mitigation: Cache invalidation

**LocalSync loop**
- Symptom: Upload triggers download triggers upload
- Impact: Infinite requests
- Mitigation: Track `lastChangeSource`

#### 4. Azure Deployment Failures

**Old code cached (Oryx)**
- Symptom: UNKNOWN_MESSAGE for CREATE_FILE
- Root Cause: Old build cached
- Solution: Remove oryx-manifest.toml

**Deploy script missing copy**
- Symptom: Code built but not deployed
- Root Cause: No `cp` to wwwroot
- Solution: Add copy step to deploy.sh

**Node.js memory cache**
- Symptom: Restart doesn't load new code
- Root Cause: Soft restart keeps cache
- Solution: Full STOP/START from portal

---

## Summary

### Architecture Highlights

1. **Server**: WebSocket server on Azure with lock-based file management
2. **Extension**: VS Code FileSystemProvider + bidirectional sync
3. **CREATE_FILE**: Complete flow from local detection to server creation to broadcast
4. **Testing**: Comprehensive test points for success and failure paths

### Success Criteria

✅ File created on server with correct content
✅ Parent directories auto-created
✅ Creator gets lock and FILE_SNAPSHOT
✅ All clients receive TREE_SNAPSHOT
✅ LocalSync prevents re-upload via metadata
✅ VS Code UI reflects changes

---

**End of Architecture Documentation**
