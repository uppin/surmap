---
description: Collaborative visual debugging when struggling with technical issues
---
# Visual Inspection Mode - Collaborative Visual Debugging

## Purpose
This mode is activated when the **Assistant is struggling to troubleshoot a technical issue** and needs **human visual inspection** to provide feedback for faster problem resolution.

## Core Principle: Human-AI Collaborative Debugging
The Assistant should focus on **creating visibility** for the human to visually inspect partial and final results, then provide feedback to guide the troubleshooting process.

## What "Visibility" Means
- **Save intermediate files** with clear, descriptive paths in `tmp/visual-inspection/{current-date}/`
- **Generate visual artifacts** (images, sessions, logs, etc.) that humans can open and inspect
- **Preserve debug outputs** instead of cleaning them up
- **Add comprehensive logging** with human-readable context
- **Create side-by-side comparisons** when applicable
- **Export data in formats** humans can easily review (text files, images, structured logs)

## Assistant Responsibilities in Debug Mode

### 1. **Create Visual Inspection Points**
```
✅ Create directory: mkdir -p tmp/visual-inspection/$(date +%Y-%m-%d)/
✅ Save input files: tmp/visual-inspection/$(date +%Y-%m-%d)/debug-input-[timestamp].ext
✅ Save output files: tmp/visual-inspection/$(date +%Y-%m-%d)/debug-output-[timestamp].ext
✅ Save intermediate results: tmp/visual-inspection/$(date +%Y-%m-%d)/debug-step[N]-[description].ext
✅ Print all file paths clearly to console
✅ Include timestamps and descriptions in filenames
```

### 2. **Enhance Debug Logging**
```
✅ Add detailed comments explaining what should happen vs. what actually happens
✅ Log key variables and their values at decision points
✅ Include context about expected vs. actual behavior
✅ Use clear, descriptive debug messages that explain the logic
```

### 3. **Present Results for the User Review**
```
✅ Clearly summarize what was tested
✅ Highlight specific files/areas that need visual inspection
✅ Ask targeted questions about what the human observes
✅ Provide context for what the human should look for
✅ **CRITICAL**: Provide the list of file paths in the Chat so user can click those paths and review the assets.
✅ **NEVER** generate scripts that open files - scripts close windows when they finish execution
```

### 4. **Facilitate Feedback Loop**
```
✅ Wait for human visual feedback before making major changes
✅ Use human observations to guide next debugging steps
✅ Adjust approach based on what the human reports seeing
✅ Document insights gained from visual inspection
```

## Example Visual Inspection Session Flow

1. **Assistant**: "I'm struggling with mapped landmark detection. Let me create visual debug files..."
2. **Assistant**: Creates `mkdir -p tmp/visual-inspection/2025-09-24/` and saves:
   - `tmp/visual-inspection/2025-09-24/debug-qr-input-1452.svg`
   - `tmp/visual-inspection/2025-09-24/map-snapshot-1452.png`
   - `tmp/visual-inspection/2025-09-24/debug-qr-rendered-1452.png`
3. **Assistant**: Uses `run_terminal_cmd` with `open tmp/visual-inspection/2025-09-24/debug-qr-input-1452.svg` to open files directly
4. **Assistant**: "I've opened the debug files in tmp/visual-inspection/2025-09-24/. Please tell me: Do you see the mapped landmark in the input frames? Is it visible in the map snapshot? What does the rendered map show?"
5. **Human**: Provides visual feedback about what they observe
6. **Assistant**: Uses feedback to identify the specific issue and fix it

## Critical Implementation Detail: Opening Files

**ALWAYS use direct `open` commands via `run_terminal_cmd`:**
```bash
# ✅ CORRECT - Opens file and keeps it open
open tmp/visual-inspection/2025-09-24/map-snapshot-1452.png

# ❌ WRONG - Script closes window when execution completes
echo "open tmp/visual-inspection/2025-09-24/map-snapshot.png" > script.sh && chmod +x script.sh && ./script.sh
```

The agent must invoke `open` directly through the terminal tool to ensure the opened application stays running for human inspection.

## Visual Inspection Directory Structure

### **Location and Organization**
- **Base directory**: `tmp/visual-inspection/{current-date}/` (within repository root)
- **Auto-creation**: Always create directory with `mkdir -p tmp/visual-inspection/$(date +%Y-%m-%d)/`
- **Date organization**: Files grouped by date for better chronological organization
- **File naming**: Include timestamps for session-level organization within each day
- **File types**: Support all visual formats (PNG, SVG, HTML, TXT, JSON)

### **Benefits of Repository-Based Storage**
- **Version control**: Files can be committed if needed for future reference
- **Project context**: Debug files stay with the relevant codebase
- **Team collaboration**: Shared access to debug artifacts
- **Organized cleanup**: Easy to manage debug files within project structure

### **Cleanup Recommendations**
- **Daily cleanup**: Can safely delete entire date directories after debugging sessions
- **Important findings**: Keep significant debug artifacts for documentation
- **Repository hygiene**: Add `tmp/visual-inspection/` to `.gitignore` if needed
- **Storage management**: Periodically clean up old date directories (e.g., older than 7 days)

## When NOT to Use Visual Inspection Mode
- For simple syntax errors or compilation issues
- When the problem is clear from error messages
- For routine test failures with obvious causes
- When standard debugging techniques are sufficient

## Success Criteria
- Human can visually inspect all relevant artifacts
- Human feedback leads to faster issue identification
- Collaboration reduces debugging iteration time
- Visual evidence confirms or contradicts assumptions
