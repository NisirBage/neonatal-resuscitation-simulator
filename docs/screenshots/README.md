# Screenshots

This directory holds screenshots used in the README and GitHub Pages site.

## Pending Screenshots

To complete the documentation, capture and add the following images:

| Filename | Content | Suggested Size |
|----------|---------|----------------|
| `student-dashboard.png` | Student view showing a voice prompt, YES/NO buttons, birth timer, and ventilation progress bar | 1280 × 800 |
| `instructor-dashboard.png` | Instructor view showing FSM state, override panel, live event log, and timer controls | 1280 × 800 |
| `session-replay.png` | Replay view with step-through controls and colour-coded event timeline | 1280 × 800 |
| `performance-metrics.png` | Metrics page showing training score, step timing, and metric breakdown table | 1280 × 800 |
| `pdf-report.png` | Sample PDF report open in a PDF viewer | 1280 × 900 |
| `clinical-xlsx.png` | Clinical timeline XLSX open in Excel showing colour-coded phase column | 1280 × 800 |
| `architecture-diagram.png` | Architecture diagram (can be exported from the ASCII diagram in README) | 900 × 600 |
| `demo-workflow.gif` | Animated GIF of a complete student happy path (~30 seconds, 15 fps) | 1280 × 720 |

## How to Capture

1. Start the simulator locally (`docker compose up --build` or the local dev commands from the README).
2. Use the demo sequence in [DEMO_RUNBOOK.md](../DEMO_RUNBOOK.md) to walk through each screen.
3. Take screenshots using your OS screenshot tool or a browser extension.
4. Optimise PNGs with [Squoosh](https://squoosh.app/) or `pngquant` to keep file sizes reasonable (< 500 KB per image).
5. Record the demo GIF with [LICEcap](https://www.cockos.com/licecap/) (Windows/macOS) or [Peek](https://github.com/phw/peek) (Linux).
6. Place the files in this directory and update the README image links.

## README Image Links

Once screenshots are captured, the README `![Alt](docs/screenshots/filename.png)` links will render automatically on GitHub.
