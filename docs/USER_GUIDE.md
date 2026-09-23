# User guide – Comskip for Windows

[Back to the project overview](../README.md)

This guide covers the portable Windows package and reviewing saved Comskip results in ComskipGUI. The workflow menus currently use German labels; their keys and English meanings are listed below.

## Quick start

1. Extract the complete portable package into one folder. Keep its programs, DLLs, configuration files and `_Workflow` folder together. A source-code download alone does not contain the executables; see [BUILDING.md](../BUILDING.md) to build them.
2. Install Python 3 for the menu-based workflow. Install Avidemux if you want to use the supplied final-editing workflow; its executable must be discoverable through `PATH` or a supported standard installation location.
3. Open `_Workflow/Werbung entfernen Start.bat`. The initial recording folder is your Windows Downloads folder. Press **V** to select another folder for this session. The batch workflow lists **MP4 recordings** in that folder.
4. Press **A** to analyse recordings and then review the open results. Broadcaster profiles are selected automatically from the filename and the configured station lists.
5. In ComskipGUI, use **N/M** to visit boundaries, **Left/Right** to fine-tune the position, and **B/E** to correct a commercial block's beginning/end.
6. Press **W** to save, then **Esc** to close the GUI. Back in the console, choose **C** to prepare editing with the confirmed commercial blocks or **M** for fully manual editing.
7. Open the generated Avidemux launcher beside the recording, check the programme's beginning and end, and save the edited video in Avidemux.

**ComskipGUI saves cut instructions. Saving in the GUI does not itself cut the video.**

## Workflow menu

Enter these keys in the console menu, followed by Enter.

| Key | Menu label | Action |
| --- | --- | --- |
| A | Analysieren und danach offene Filme prüfen | Analyse recordings, then review results that still need a decision. |
| N | Nur analysieren | Analyse only; review later with P. |
| P | Nur offene Filme prüfen | Start or resume reviewing undecided recordings. |
| E | Film auswählen / erneut prüfen | Select a recording, including one already reviewed, to inspect it again. |
| R | Einen Film gezielt neu analysieren | Reanalyse one recording. Its previous analysis and editing decision are backed up first. At the confirmation prompt, J means Yes and N means No. |
| V | Verzeichnis für diesen Durchlauf wählen | Choose the recording folder for this session. |
| Q | Beenden | Exit. |

During analysis, **B** finishes the current recording and then stops the batch; **X** or **Ctrl+C** cancels the current analysis and returns to the menu. These keys have different meanings inside ComskipGUI.

## ComskipGUI keyboard reference

Click the GUI window before using these controls. Letter keys do not require Shift. The editing commands below apply when reviewing a saved Comskip `.txt` result, as opened by the supplied workflow.

| Key or control | Action |
| --- | --- |
| Mouse click / drag on timeline | Jump to a position / move through the recording. |
| Left / Right | Move backward / forward by one frame. |
| Down / Up | Move backward / forward by one second. |
| Page Down / Page Up | Move backward / forward by 20 seconds. |
| N / M | Jump to the previous / next commercial boundary, including the recording edges. |
| S / F | Jump to the start / finish of the recording. |
| Z / U | Zoom into / out of the timeline. |
| B | Set the relevant commercial block's beginning to the current frame. |
| E | Set the relevant commercial block's end to the current frame. |
| I | Insert a new block anchor at the current frame, outside an existing block. |
| D | Delete the commercial block containing the current frame. |
| Ctrl+Z | Undo an edit, up to 10 steps since the last save. |
| W | Save the cut list. Saving clears the undo history. |
| Esc | Close the review; unsaved changes trigger a save confirmation. |
| F1 | Show built-in help; press another key to dismiss it. |
| F5 | Cycle the position display between frame and time formats. |
| J / K | Set temporary before / after markers; with both set, jump halfway between them. |
| L | Clear the temporary J/K markers. |

**Remember: N/M navigate; B/E edit; W saves.** J/K markers only help locate a transition; use B/E to change the actual cut boundaries.

## Correcting the results

### Adjust an existing commercial block

Use N/M to reach the block boundary, then the arrow keys to find the correct transition. Press **B** at the intended block beginning or **E** at its intended end. Check both sides of the transition. Use Ctrl+Z immediately if you change the wrong boundary.

### Add a missed block

Move to the beginning of the missed commercial section and press **I**. This creates an orange anchor at the current frame. Move forward to the section's end and press **E** to give the block its full length. An anchor by itself is not a finished commercial interval.

### Remove a false detection

Move inside the incorrectly marked block and press **D**. This removes the block from the cut list so that the section will be kept.

### Correct programme start and end

Fast boundary mode produces two approximate outer blocks and does not look for internal advertising. At the opening transition, use **E** to adjust the end of the first block. At the closing transition, use **B** to adjust the beginning of the last block. Review these positions before accepting them.

### Save and continue

Press **W**, then **Esc**. If the save confirmation appears, **Ja** means save, **Nein** means discard unsaved edits, and **Abbrechen** means continue reviewing.

After closing the GUI, the console asks for an editing decision:

| Key | Action |
| --- | --- |
| C – Crop | Generate an Avidemux project using the confirmed commercial blocks and a matching `_Avidemux_CROP_Start.bat` launcher. |
| M – Manuell | Generate an `_Avidemux_MANUELL_Start.bat` launcher for fully manual editing, without applying automatic commercial cuts. |
| S – Skip | Leave this recording undecided and continue with the next one. |
| Q – Quit | Stop the review; the current recording stays open for later review with P. |

The generated launchers are placed beside the recording. In Avidemux, check the remaining programme and trim its outer edges if needed before saving. When reopening an already decided recording through **E**, the console also offers Enter to keep the existing decision.

## Broadcaster profiles

Edit the station lists beside `comskip-final.exe` with a text editor. Use one broadcaster token per line; lines starting with `#` are comments.

- **`Schnellmodus-Sender.txt`:** only use this for broadcasts where you expect no internal commercial breaks. It creates programme-boundary suggestions only.
- **`Makromodus-Sender.txt`:** selects the fast commercial logo macro mode for matching broadcasters.
- **WeDo Movies:** selected by the exact, case-sensitive filename token `wedo-movies`.
- **Other recordings:** use the general full-analysis path.

Station tokens must match the broadcaster portion of the recording filename. Preserve the broadcaster information supplied by your TV recorder. Advanced detection settings remain available through command-line options and code; there is no graphical profile editor.

## Use without the menu workflow

From PowerShell in the complete portable Comskip folder, run `comskip-final.exe` with the recording path to analyse a single file. Then open its matching `.txt` result with `ComskipGUI.exe`:

```powershell
.\comskip-final.exe "D:\Recordings\recording.mp4"
.\ComskipGUI.exe "D:\Recordings\recording.txt"
```

Replace the paths with your recording and result paths. Keep the video and its matching result files together. For the available analysis options, run `.\comskip-final.exe --help`.

`--full-analysis` bypasses the commercial macro profile; it does not override the dedicated public-broadcaster or WeDo profiles.
