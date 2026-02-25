# Phase 0 Setup and Testing Guide

This guide walks you through setting up and testing the collaborative workspace system (Phase 0).

## Overview

Phase 0 consists of:
1. **WebSocket Server** (`collab-server/`) - Manages file storage, locking, and real-time sync
2. **VS Code Extension** (`extensions/collab-workspace/`) - Client that connects to server

## Prerequisites

- Node.js 20+ installed
- VS Code (for running the extension)
- Two terminal windows (one for server, one for commands)

## Step 1: Install Server Dependencies

```bash
cd collab-server
npm install
```

## Step 2: Install Extension Dependencies

```bash
cd extensions/collab-workspace
npm install
```

## Step 3: Start the Server

In terminal 1:

```bash
cd collab-server
npm run dev
```

You should see:
```
============================================================
Collaborative Workspace Server - Phase 0
============================================================
Host: localhost
Port: 8080
Workspace Root: ./storage/workspaces
============================================================
[Server] WebSocket server listening on ws://localhost:8080
```

Leave this running.

## Step 4: Compile the Extension

In terminal 2:

```bash
cd extensions/collab-workspace
npm run compile
```

## Step 5: Launch Extension in VS Code

1. Open this project in VS Code
2. Open [extensions/collab-workspace/src/extension.ts](extensions/collab-workspace/src/extension.ts)
3. Press **F5** to launch Extension Development Host
4. A new VS Code window will open with the extension loaded

## Step 6: Connect to Workspace

In the new VS Code window (Extension Development Host):

1. Open Command Palette (Ctrl+Shift+P / Cmd+Shift+P)
2. Run command: **"Collaborative Workspace: Connect to Server"**
3. You should see: "Connected to collaborative workspace!"

## Step 7: Explore the Workspace

1. Look at the **Activity Bar** (left sidebar) - you should see a new "Collaborative Workspace" icon
2. Click it to open the workspace tree view
3. You should see:
   ```
   Collaborative Workspace
   └── Workspace Files
       ├── README.md
       ├── src/
       │   ├── main.ts
       │   └── utils.ts
       └── test.txt
   ```

## Step 8: Open and Edit Files

1. Click on `test.txt` in the tree
2. The file opens in the editor
3. Make some changes
4. Save (Ctrl+S / Cmd+S)
5. Check the server terminal - you should see logs about file updates

## Step 9: Test File Locking (Multi-User)

To test file locking with multiple clients:

1. Keep the first Extension Development Host window open with `test.txt` open
2. In the MAIN VS Code window (not the Extension Dev Host), press F5 again
3. A SECOND Extension Development Host window opens
4. In the second window:
   - Connect to the workspace
   - Try to open `test.txt`
   - You should see an error: "File is locked by another user"
5. Close `test.txt` in the first window
6. Now try opening it again in the second window - it should work!

## Step 10: Test Live Updates

1. Keep both Extension Development Host windows connected
2. In window 1: Open `README.md`
3. In window 2: Open `src/main.ts` (different file)
4. In window 1: Edit and save `README.md`
5. Watch the server logs - you should see the update broadcast
6. Other clients don't see changes in Phase 0 since they can't open locked files

Note: Full multi-user concurrent editing comes in Phase 2 with Yjs.

## Troubleshooting

### Server won't start

- Check if port 8080 is already in use
- Try changing `PORT` in `collab-server/.env`

### Extension won't connect

- Ensure server is running
- Check server URL in VS Code settings: `collabWorkspace.serverUrl`
- Check browser/extension console for errors

### Files don't appear in tree

- Check that files exist in `collab-server/storage/workspaces/ws_default/files/`
- Try the "Refresh Tree" command

### Can't save files

- Make sure you opened the file by clicking it in the tree (this acquires the lock)
- Check that you're connected to the server

### Extension not loading

- Make sure you compiled it: `npm run compile` in extension folder
- Check the Extension Host output panel for errors

## Success Criteria

Phase 0 is working correctly if:

- ✅ Server starts and accepts connections
- ✅ Extension connects to server
- ✅ Folder tree appears in VS Code sidebar
- ✅ Files can be opened from tree
- ✅ File edits save and persist
- ✅ Second client sees "file locked" error
- ✅ Server logs show all operations

## Next Steps

After Phase 0 works:
- **Phase 1**: Multi-user tree sync, folder operations, PostgreSQL, user accounts
- **Phase 2**: Yjs collaborative editing, presence cursors, AI agent

## File Locations

- Server code: [collab-server/src/](collab-server/src/)
- Extension code: [extensions/collab-workspace/src/](extensions/collab-workspace/src/)
- Test workspace: [collab-server/storage/workspaces/ws_default/files/](collab-server/storage/workspaces/ws_default/files/)
- Server config: [collab-server/.env](collab-server/.env)

## Configuration

Extension settings (in VS Code settings.json):

```json
{
  "collabWorkspace.serverUrl": "ws://localhost:8080",
  "collabWorkspace.workspaceId": "ws_default",
  "collabWorkspace.token": "dev-admin-token-12345"
}
```

## Development Commands

Server:
```bash
cd collab-server
npm run dev      # Start with watch mode
npm run build    # Compile TypeScript
npm start        # Run compiled version
```

Extension:
```bash
cd extensions/collab-workspace
npm run compile  # Compile TypeScript
npm run watch    # Compile with watch mode
```
