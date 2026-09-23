# Comskip – Improved GUI & Enhanced Logo Detection

**A Comskip fork for faster commercial detection and a much better editing experience.**

Comskip identifies commercial breaks in TV recordings. This fork builds on that foundation with two major improvements: a substantially improved **ComskipGUI** for reviewing and correcting cut points, and **enhanced logo detection with fast, broadcaster-specific processing paths**.

If you already use Comskip, this fork makes working with its results easier and more precise. If you are looking for commercial-detection software for television recordings, it provides automatic detection and hands-on review in one workflow—particularly for raw recordings from online TV recorders such as **YouTV**, including recordings with extra material before and after the programme.

**New here?** Read the [Quick start](#quick-start) or the [English user guide and keyboard reference](docs/USER_GUIDE.md).

## 1. A substantially better ComskipGUI

Automatic detection is only part of the job. Checking a recording and correcting its cut points should be quick, clear and reliable. Improving that everyday experience is the first major focus of this fork.

- **A clearer timeline:** more visible commercial blocks, boundaries and navigation markers make it easier to see what will be kept and what will be removed.
- **More practical navigation:** click or drag along the timeline, move through individual frames, use short or longer time jumps, and jump directly between commercial boundaries.
- **More comfortable viewing:** improved use of the maximized window and smoother redraws make navigating a recording less distracting.
- **Precise, stable cut points:** adjust block starts and ends at the selected frame. Corrected frame mapping keeps saved boundaries from shifting when results are reopened.
- **Easier corrections:** insert a block at the current position, adjust or delete blocks, and undo recent edits with **Ctrl+Z**.
- **Protection against accidental loss of edits:** a save confirmation appears when leaving a review with unsaved changes.

The benefit is direct: less time wrestling with the interface and more control over the final cut. The improved GUI is a reason to use this fork even if your main interest is Comskip's existing detection workflow.

## 2. Enhanced logo detection, with faster analysis paths

This fork extends Comskip's logo detection to better handle untrimmed TV recordings and to reduce analysis time where a focused detection path is sufficient.

Depending on the selected profile, it can learn a station logo dynamically from the recording, compare candidates from several learning windows, and combine Comskip's edge-based logo detector with an independent logo sensor. Learning from the programme itself reduces the influence of unrelated material at the recording's beginning and end.

The fast paths use coarse sampling to locate relevant sections, then examine transition regions in more detail. This can make analysis substantially faster than processing the entire recording with the full Comskip pipeline. The actual gain depends on the broadcaster, recording and selected profile.

## 3. Different broadcasters, different detection stages

TV recordings do not all need the same analysis. This fork adds broadcaster-specific profiles with their own detection stages:

| Processing profile | What it does for you |
| --- | --- |
| **Fast boundary mode** | For configured broadcasters carrying programmes without internal commercial breaks, identifies approximate programme-start and programme-end boundaries for quick manual adjustment. |
| **Commercial logo macro mode** | Learns the logo from the current recording, finds broad programme and commercial sections, and refines the transitions locally. |
| **WeDo Movies detection** | Uses a dedicated recognition path for WeDo promotional layouts and the return to the movie, combining a coarse search with local verification. |
| **Full analysis** | Combines enhanced logo analysis with Comskip's existing detection signals and block-processing logic for recordings that need the general processing path. |

The launcher selects the appropriate primary profile from configured broadcaster tokens in the filename. Each profile runs its own processing stages; recordings do not simply pass through every detector. The commercial macro and WeDo fast paths include automatic fallback to their fuller analysis paths when needed.

**These extensions are already implemented.** Broadcaster lists can be edited in `Schnellmodus-Sender.txt` and `Makromodus-Sender.txt`; the WeDo path recognizes the filename token `wedo-movies`. More advanced behaviour is configured through command-line options and code. With some technical know-how, you can adapt the detection to your recordings. There is currently no unified graphical editor for these settings.

## Quick start

1. Open `_Workflow/Werbung entfernen Start.bat` in the complete portable Windows package.
2. Press **V** to choose your MP4 recording folder, then **A** to analyse and review.
3. In ComskipGUI, use **N/M** to jump between boundaries and **Left/Right** for frame-by-frame adjustment.
4. Use **B/E** to set a block's beginning/end, **I/D** to insert/delete a block, and **Ctrl+Z** to undo.
5. Press **W** to save and **Esc** to close. Choose **C** in the console to prepare an Avidemux project with the confirmed cuts, or **M** for manual editing.
6. Open the generated Avidemux launcher beside the recording, check the programme edges, and save the edited video.

**[Read the English user guide](docs/USER_GUIDE.md)** for setup, the full keyboard reference, editing instructions and broadcaster settings. It also explains the workflow's current German menu labels in English. Saving in ComskipGUI saves the cut list; the video is cut in the subsequent editing step.

## Working with your recordings

The intended workflow is straightforward: **analyse a recording, review the detected blocks in the improved GUI, correct any boundaries, and use the saved cut list for the final video cut.**

Automatic detection can still need correction, particularly around trailers, station promotions or changing logos. The improved review interface makes that final check a practical part of the workflow.

The portable Windows package includes the Comskip engine, ComskipGUI, the enhanced analysis launcher and the supporting workflow. Start the included workflow with `_Workflow/Werbung entfernen Start.bat`. The workflow requires Python 3 and the video-processing tools described in the package documentation.

Source-build requirements and instructions are in [BUILDING.md](BUILDING.md).

## Upstream and license

This project is a fork of [Comskip](https://github.com/erikkaashoek/Comskip), extending its commercial-detection engine and review interface. See [LICENSE](LICENSE) for the project license; bundled third-party components retain their respective licenses.
