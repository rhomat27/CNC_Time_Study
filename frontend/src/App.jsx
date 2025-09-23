import React, { useState } from "react";
import axios from "axios";

function App() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const [config, setConfig] = useState({
    rapid_accel_g: 1.0,
    cut_accel_g: 0.5,
    pierce_time: 1.0,
    lifter_time: 0.5,
    default_rapid_ipm: 500,
    default_cut_ipm: 100,
    beam_on_code: "M07",
    beam_off_code: "M08",
    inch_mode_code: "G70",
    metric_mode_code: "G71",
    abs_mode_code: "G90",
    rel_mode_code: "G91",
    followProgramArcs: false,
  });

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      setError("Please select a G-code file.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    Object.keys(config).forEach((key) => {
      formData.append(key, config[key]);
    });

    try {
      const res = await axios.post(
        process.env.REACT_APP_API_URL || "http://192.168.254.135:8009/analyze",
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        }
      );
      setResult(res.data);
      setError(null);
    } catch (err) {
      console.error(err);
      setError("Upload failed. Check backend connectivity.");
    }
  };

  return (
    <div style={{ padding: "20px" }}>
      <h1>CNC Time Study</h1>
      <form onSubmit={handleSubmit}>
        <input type="file" onChange={handleFileChange} accept=".nc,.gcode,.txt" />
        <h3>Machine Motion</h3>
        <div>
          Rapid Accel (G):{" "}
          <input
            type="number"
            step="0.1"
            value={config.rapid_accel_g}
            onChange={(e) =>
              setConfig({ ...config, rapid_accel_g: e.target.value })
            }
          />
        </div>
        <div>
          Cut Accel (G):{" "}
          <input
            type="number"
            step="0.1"
            value={config.cut_accel_g}
            onChange={(e) =>
              setConfig({ ...config, cut_accel_g: e.target.value })
            }
          />
        </div>
        <div>
          Pierce Time (s):{" "}
          <input
            type="number"
            step="0.1"
            value={config.pierce_time}
            onChange={(e) =>
              setConfig({ ...config, pierce_time: e.target.value })
            }
          />
        </div>
        <div>
          Lifter Time (s):{" "}
          <input
            type="number"
            step="0.1"
            value={config.lifter_time}
            onChange={(e) =>
              setConfig({ ...config, lifter_time: e.target.value })
            }
          />
        </div>
        <div>
          Default Rapid (IPM):{" "}
          <input
            type="number"
            value={config.default_rapid_ipm}
            onChange={(e) =>
              setConfig({ ...config, default_rapid_ipm: e.target.value })
            }
          />
        </div>
        <div>
          Default Cut (IPM):{" "}
          <input
            type="number"
            value={config.default_cut_ipm}
            onChange={(e) =>
              setConfig({ ...config, default_cut_ipm: e.target.value })
            }
          />
        </div>
        <h3>Beam Control</h3>
        <div>
          Beam ON Code:{" "}
          <input
            type="text"
            value={config.beam_on_code}
            onChange={(e) =>
              setConfig({ ...config, beam_on_code: e.target.value })
            }
          />
        </div>
        <div>
          Beam OFF Code:{" "}
          <input
            type="text"
            value={config.beam_off_code}
            onChange={(e) =>
              setConfig({ ...config, beam_off_code: e.target.value })
            }
          />
        </div>
        <h3>Modes</h3>
        <div>
          Inch Mode Code:{" "}
          <input
            type="text"
            value={config.inch_mode_code}
            onChange={(e) =>
              setConfig({ ...config, inch_mode_code: e.target.value })
            }
          />
        </div>
        <div>
          Metric Mode Code:{" "}
          <input
            type="text"
            value={config.metric_mode_code}
            onChange={(e) =>
              setConfig({ ...config, metric_mode_code: e.target.value })
            }
          />
        </div>
        <div>
          Absolute Mode Code:{" "}
          <input
            type="text"
            value={config.abs_mode_code}
            onChange={(e) =>
              setConfig({ ...config, abs_mode_code: e.target.value })
            }
          />
        </div>
        <div>
          Relative Mode Code:{" "}
          <input
            type="text"
            value={config.rel_mode_code}
            onChange={(e) =>
              setConfig({ ...config, rel_mode_code: e.target.value })
            }
          />
        </div>
        <div>
          <label>
            <input
              type="checkbox"
              checked={config.followProgramArcs}
              onChange={(e) =>
                setConfig({ ...config, followProgramArcs: e.target.checked })
              }
            />
            Arc Centers Follow Program Coordinates (G90/G91)
          </label>
        </div>
        <button type="submit">Analyze</button>
      </form>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {result && (
        <div>
          <h3>Results for {result.filename}</h3>
          <ul>
            <li>Cut Time: {result.cut_time_sec}s</li>
            <li>Travel Time: {result.travel_time_sec}s</li>
            <li>Pierce Time: {result.pierce_time_sec}s</li>
            <li>Dwell Time: {result.dwell_time_sec}s</li>
            <li>Lifter Time: {result.lifter_time_sec}s</li>
            <li>Total Time: {result.total_time_sec}s</li>
            <li>Pierce Count: {result.pierce_count}</li>
            <li>Beam Cycles: {result.beam_cycles}</li>
            {result.final_modes && (
              <li>
                Final Mode: {result.final_modes.units} units,{" "}
                {result.final_modes.positioning}
              </li>
            )}
          </ul>
          <h3>Toolpath Preview</h3>
          <svg width="400" height="400" style={{ border: "1px solid black" }}>
            {result.toolpath.map((seg, idx) => (
              <line
                key={idx}
                x1={seg.points[0][0]}
                y1={400 - seg.points[0][1]}
                x2={seg.points[1][0]}
                y2={400 - seg.points[1][1]}
                stroke={seg.type === "cut" ? "red" : "blue"}
                strokeWidth="1"
              />
            ))}
          </svg>
        </div>
      )}
    </div>
  );
}

export default App;