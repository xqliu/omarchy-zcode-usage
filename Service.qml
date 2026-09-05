import QtQuick
import Quickshell
import Quickshell.Io

// Headless service: periodically runs the bundled collector.py and installs
// its JSON record into ~/.local/state/omarchy/agents/usage/zcode.json, where
// the built-in omarchy.agents panel discovers and displays it. The panel
// never learns how the numbers were made — a record that appears in the
// usage directory is an agent, whoever wrote it.

Item {
  id: root

  readonly property string home: Quickshell.env("HOME") || ""
  readonly property string usageDir: (Quickshell.env("XDG_STATE_HOME") || home + "/.local/state") + "/omarchy/agents/usage"
  readonly property string recordPath: usageDir + "/zcode.json"

  // Collector ships inside the plugin folder; resolve the file path from its
  // resource URL so the plugin works wherever omarchy installs it.
  readonly property string collectorPath: decodeURIComponent(Qt.resolvedUrl("collector.py").toString().replace(/^file:\/\//, ""))

  // First successful write of the session: the agents panel only rescans the
  // usage directory at shell start and after its own update runs, so nudge it
  // once to make a freshly installed plugin appear immediately.
  property bool nudgedPanel: false

  FileView {
    id: recordFile
    path: root.recordPath
    watchChanges: false
    atomicWrites: true
    printErrors: false
  }

  Process {
    id: mkdirProcess
    running: false
    command: ["mkdir", "-p", root.usageDir]
    onExited: function(exitCode) {
      if (exitCode === 0) collectorProcess.running = true
    }
  }

  Process {
    id: collectorProcess
    running: false
    command: ["python3", root.collectorPath]

    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: recordFile.setText(text.trim() + "\n")
    }

    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("zcode-usage", text.trim())
    }

    onExited: function(exitCode) {
      if (exitCode === 0 && !root.nudgedPanel) {
        root.nudgedPanel = true
        nudgeProcess.running = true
      }
    }
  }

  Process {
    id: nudgeProcess
    running: false
    command: ["omarchy-shell", "omarchy.agents", "refresh"]
  }

  Timer {
    interval: 300000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: if (!mkdirProcess.running && !collectorProcess.running) mkdirProcess.running = true
  }
}
