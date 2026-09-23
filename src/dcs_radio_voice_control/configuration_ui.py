"""Local browser configuration for microphone, matching, Whisper, and HOTAS PTT."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import threading
from typing import Any
import webbrowser

from .audio_cues import play_cue
from .audio_output import AudioOutput
from .autostart import registration_status, set_enabled as set_autostart_enabled
from .desktop_shortcut import shortcut_status, set_enabled as set_shortcut_enabled
from .configuration_store import (
    CUE_VOLUME_RANGE,
    MINIMUM_LEAD_RANGE,
    MINIMUM_SCORE_RANGE,
    config_path,
    load_document,
    save_document,
    update_settings,
)
from .event_log import log_directory, recent_events, write_event
from .controller_state import get_state
from .hotas import SdlHotasInput, learn_binding, resolve_binding, wait_for_release
from .microphone import WinMmAudioInput
from .stt import PROJECT_ROOT
from .tts import PiperSpeech


HOST = "127.0.0.1"
PORT = 34385


class ConfigurationApplication:
    def __init__(self) -> None:
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        self.audio = WinMmAudioInput()
        self.hotas = SdlHotasInput()

    def status(self) -> dict[str, Any]:
        document = load_document()
        controllers = self.hotas.devices()
        models = {path.name for path in (PROJECT_ROOT / "stt").glob("ggml-*.bin")}
        models.add(str(document["stt"]["model"]))
        compute = "cpu"
        try:
            manifest = json.loads((PROJECT_ROOT / "stt" / "dcs_radio_voice_control-stt.json").read_text(encoding="utf-8-sig"))
            if isinstance(manifest, dict) and manifest.get("compute") == "cuda12":
                compute = "cuda12"
        except (OSError, json.JSONDecodeError):
            pass
        return {
            "config": document,
            "config_path": str(config_path()),
            "log_path": str(log_directory()),
            "microphones": [asdict(device) for device in self.audio.microphones()],
            "controllers": [asdict(device) for device in controllers],
            "outputs": AudioOutput.devices(),
            "stt_compute": compute,
            "models": sorted(models),
            "score_range": MINIMUM_SCORE_RANGE,
            "lead_range": MINIMUM_LEAD_RANGE,
            "cue_volume_range": CUE_VOLUME_RANGE,
            "events": recent_events(30),
            "autostart": registration_status(),
            "desktop_shortcut": shortcut_status(),
            "controller": get_state(),
        }

    def save(self, request: dict[str, Any]) -> dict[str, Any]:
        microphones = self.audio.microphones()
        microphone_id = request.get("microphone_id")
        microphone = next((item for item in microphones if item.device_id == microphone_id), None)
        if microphone is None:
            raise ValueError("Select a currently connected microphone.")
        model = request.get("model")
        available_models = {path.name for path in (PROJECT_ROOT / "stt").glob("ggml-*.bin")}
        available_models.add(str(load_document()["stt"]["model"]))
        if model not in available_models:
            raise ValueError("Select an installed Whisper model.")
        if request.get("use_gpu") and self.status()["stt_compute"] != "cuda12":
            raise ValueError("Install the CUDA worker before enabling GPU recognition.")
        output_device = request.get("output_device") or None
        if output_device is not None and output_device not in AudioOutput.devices():
            raise ValueError("Select a currently connected audio output.")
        original = load_document()
        start_with_windows = request.get("start_with_windows")
        shortcut_before = shortcut_status()["exists"]
        desktop_shortcut = request.get("desktop_shortcut", shortcut_before)
        if not isinstance(desktop_shortcut, bool):
            raise ValueError("Desktop shortcut must be enabled or disabled.")
        document = update_settings(
            original,
            minimum_score=request.get("minimum_score"),
            minimum_lead=request.get("minimum_lead"),
            model=model,
            use_gpu=request.get("use_gpu"),
            output_device=output_device,
            microphone=asdict(microphone),
            audio_cues=request.get("audio_cues"),
            cue_volume=request.get("cue_volume"),
            start_with_windows=start_with_windows,
        )
        target = save_document(document)
        try:
            set_autostart_enabled(start_with_windows)
            set_shortcut_enabled(desktop_shortcut)
        except (OSError, ValueError):
            try:
                set_autostart_enabled(bool(original["startup"]["start_with_windows"]))
                set_shortcut_enabled(bool(shortcut_before))
            finally:
                save_document(original)
            raise
        write_event("configuration_saved", message=str(target))
        return self.status()

    def learn_hotas(self) -> dict[str, Any]:
        binding = learn_binding(self.hotas, timeout=20.0)
        wait_for_release(self.hotas, binding)
        document = load_document()
        document["ptt"] = binding.document()
        save_document(document)
        write_event("ptt_assigned", ptt=f"{binding.name} button {binding.button}")
        return {"binding": binding.document(), "status": self.status()}

    def use_keyboard(self) -> dict[str, Any]:
        document = load_document()
        document["ptt"] = {"mode": "keyboard"}
        save_document(document)
        write_event("ptt_assigned", ptt="SPACE")
        return self.status()

    def ptt_state(self) -> dict[str, Any]:
        document = load_document()
        ptt = document["ptt"]
        if ptt["mode"] != "hotas":
            return {"configured": False, "pressed": False}
        binding = resolve_binding(self.hotas.devices(), ptt)
        pressed = binding.button in self.hotas.pressed_buttons(binding.device_id)
        return {
            "configured": True,
            "pressed": pressed,
            "label": f"{binding.name} button {binding.button}",
        }

    def microphone_test(self, request: dict[str, Any]) -> dict[str, Any]:
        microphone_id = request.get("microphone_id")
        microphone = next(
            (item for item in self.audio.microphones() if item.device_id == microphone_id),
            None,
        )
        if microphone is None:
            raise ValueError("Select a currently connected microphone.")
        levels = list(self.audio.levels(microphone.device_id, 3.0))
        peak = max(levels, default=0.0)
        average = sum(levels) / len(levels) if levels else 0.0
        return {"peak_dbfs": _dbfs(peak), "average_dbfs": _dbfs(average)}

    def cue_test(self, request: dict[str, Any]) -> dict[str, Any]:
        outcome = request.get("outcome")
        volume = request.get("volume")
        if outcome not in {"accepted", "rejected"}:
            raise ValueError("Select an accepted or rejected cue.")
        if isinstance(volume, bool) or not isinstance(volume, (int, float)):
            raise ValueError("Cue volume must be a number.")
        if not CUE_VOLUME_RANGE[0] <= float(volume) <= CUE_VOLUME_RANGE[1]:
            raise ValueError("Cue volume is outside the configured range.")
        output_device = request.get("output_device") or None
        if not play_cue(
            outcome,
            volume=float(volume),
            output=AudioOutput(output_device),
        ):
            raise OSError("Windows could not play the audio cue.")
        return {"played": True}

    def voice_test(self, request: dict[str, Any]) -> dict[str, Any]:
        speech = PiperSpeech(output_device=request.get("output_device") or None)
        speech.speak("DCS Radio Voice Control ready. Flight, rejoin formation.")
        return {"played": True}


def _dbfs(level: float) -> float | None:
    return round(20 * math.log10(level), 1) if level > 0 else None


class ConfigurationHandler(BaseHTTPRequestHandler):
    server: "ConfigurationServer"

    def do_GET(self) -> None:
        try:
            if self.path == "/":
                page = PAGE.replace("__TOKEN__", self.server.token)
                page = page.replace(
                    "__START_AFTER_SAVE__",
                    "true" if self.server.start_after_save else "false",
                )
                self._html(page)
            elif self.path == "/api/status":
                self._json(self.server.application.status())
            elif self.path == "/api/ptt-state":
                self._json(self.server.application.ptt_state())
            elif self.path == "/api/logs":
                self._json({"events": recent_events(100), "controller": get_state()})
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (OSError, ValueError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:
        if self.headers.get("X-DCS-Radio-Voice-Control-Token") != self.server.token:
            self._json({"error": "Invalid local configuration token."}, HTTPStatus.FORBIDDEN)
            return
        try:
            request = self._request_json()
            start_requested = False
            if self.path in {"/api/settings", "/api/settings/start"}:
                if self.path == "/api/settings/start" and not self.server.start_after_save:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                result = self.server.application.save(request)
                start_requested = self.path == "/api/settings/start"
            elif self.path == "/api/hotas/learn":
                result = self.server.application.learn_hotas()
            elif self.path == "/api/hotas/keyboard":
                result = self.server.application.use_keyboard()
            elif self.path == "/api/microphone/test":
                result = self.server.application.microphone_test(request)
            elif self.path == "/api/cue/test":
                result = self.server.application.cue_test(request)
            elif self.path == "/api/voice/test":
                result = self.server.application.voice_test(request)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._json(result)
            if start_requested:
                self.server.request_start()
        except (OSError, ValueError, TimeoutError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _request_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 64 * 1024:
            raise ValueError("Request is too large.")
        try:
            value = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Request is not valid JSON.") from exc
        if not isinstance(value, dict):
            raise ValueError("Request must be a JSON object.")
        return value

    def _json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _html(self, value: str) -> None:
        payload = value.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


class ConfigurationServer(HTTPServer):
    def __init__(
        self,
        application: ConfigurationApplication,
        *,
        start_after_save: bool = False,
    ) -> None:
        super().__init__((HOST, PORT), ConfigurationHandler)
        self.application = application
        self.token = secrets.token_urlsafe(24)
        self.start_after_save = start_after_save
        self.start_requested = False

    def request_start(self) -> None:
        self.start_requested = True
        threading.Thread(target=self.shutdown, daemon=True).start()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-after-save",
        action="store_true",
        help="close configuration after saving so the installer can start voice control",
    )
    args = parser.parse_args()
    server: ConfigurationServer | None = None
    try:
        application = ConfigurationApplication()
        server = ConfigurationServer(
            application,
            start_after_save=args.start_after_save,
        )
        address = f"http://{HOST}:{PORT}/"
        print("DCS Radio Voice Control configuration")
        print(f"Opening {address}")
        print(f"Configuration: {config_path()}")
        print(f"Logs: {log_directory()}")
        if args.start_after_save:
            print("Save configuration in the browser to start DCS Radio Voice Control.")
        else:
            print("Close this window or press Ctrl+C when setup is complete.")
        webbrowser.open(address)
        server.serve_forever()
        if server.start_requested:
            print("Configuration saved. Starting DCS Radio Voice Control.")
            return 10
        return 0
    except KeyboardInterrupt:
        print("\nConfiguration closed.")
        return 0
    except OSError as exc:
        print(f"Configuration failed: {exc}")
        return 2
    finally:
        if server is not None:
            server.server_close()


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DCS Radio Voice Control configuration</title>
<style>
:root{color-scheme:dark;--bg:#0d1117;--panel:#161b22;--line:#30363d;--text:#e6edf3;--muted:#8b949e;--accent:#58a6ff;--ok:#3fb950;--bad:#f85149}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,sans-serif}.wrap{max-width:980px;margin:auto;padding:32px 20px}h1{margin:0 0 4px;font-size:28px}h2{font-size:18px;margin:0 0 18px}.sub,.hint{color:var(--muted)}h3{font-size:15px;margin:0 0 8px}.audio-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:24px}.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:20px}.wide{grid-column:1/-1}label{display:block;margin:14px 0 6px}select,input[type=range],button{width:100%}select,button{background:#21262d;color:var(--text);border:1px solid var(--line);border-radius:6px;padding:10px}button{cursor:pointer;font-weight:600;margin-top:10px}button.primary{background:#1f6feb;border-color:#388bfd}button:hover{border-color:var(--accent)}.value{float:right;color:var(--accent)}.status{margin-top:12px;padding:10px;border-radius:6px;background:#0d1117;min-height:42px}.pressed{background:#123d20;color:#7ee787}.error{color:#ff7b72}.paths{font-size:12px;color:var(--muted);word-break:break-all}.log{max-height:280px;overflow:auto;font:12px/1.5 ui-monospace,monospace;background:#0d1117;padding:10px;border-radius:6px}.log div{border-bottom:1px solid #21262d;padding:3px 0}@media(max-width:720px){.grid,.audio-grid{grid-template-columns:1fr}.wide{grid-column:auto}}
</style></head><body><main class="wrap"><h1>DCS Radio Voice Control</h1><div class="sub">Local voice-command configuration</div>
<div class="grid">
<section class="card wide"><h2>Audio devices</h2><div class="audio-grid"><div><h3>Microphone input</h3><label for="microphone">Recording device</label><select id="microphone"></select><button id="micTest">Run three-second level test</button><div id="micResult" class="status">No test run.</div></div><div><h3>Speech and cue output</h3><label for="output">Playback device</label><select id="output"></select><button id="testVoice">Test Alan voice</button><h3>Audio feedback</h3><label><input id="audioCues" type="checkbox"> Play accepted and rejected cues</label><label>Cue volume <span id="cueValue" class="value"></span></label><input id="cueVolume" type="range" step="0.05"><button id="testAccepted">Test accepted cue</button><button id="testRejected">Test rejected cue</button></div></div></section>
<section class="card"><h2>Push to talk</h2><div id="pttCurrent" class="status">Loading…</div><div id="controllers" class="hint"></div><button id="learnPtt" class="primary">Learn a HOTAS button</button><button id="keyboardPtt">Use Space only</button><div class="hint">Learning ignores controls already held when scanning starts. Press and release the desired button.</div></section>
<section class="card"><h2>Command matching</h2><label>Minimum match <span id="scoreValue" class="value"></span></label><input id="score" type="range" step="0.01"><label>Minimum lead over runner-up <span id="leadValue" class="value"></span></label><input id="lead" type="range" step="0.01"><div class="hint">Both conditions must pass before a command is sent.</div></section>
<section class="card"><h2>Speech recognition</h2><label for="model">Installed Whisper model</label><select id="model"></select><label><input id="useGpu" type="checkbox"> Use GPU acceleration (experimental)</label><div class="hint">Install another model with setup-stt.bat small.en or medium.en. Install the optional CUDA worker with setup-stt.bat base.en cuda12. Live DCS vocabulary prompting remains enabled.</div></section>
<section class="card"><h2>Windows integration</h2><label><input id="desktopShortcut" type="checkbox"> Create a Desktop shortcut</label><div class="hint">Creates a DCS Radio Voice Control shortcut on your Windows Desktop for manual starts.</div><label><input id="startWithWindows" type="checkbox"> Start DCS Radio Voice Control with Windows</label><div class="hint">A lightweight controller waits for DCS. Whisper, Piper, the microphone, and GPU support load only after a mission and the DCS hook are ready.</div><div id="controllerState" class="status">Loading…</div></section>
<section class="card wide"><button id="save" class="primary">Save configuration</button><div id="saveResult" class="status">No unsaved changes.</div><div id="paths" class="paths"></div></section>
<section class="card wide"><h2>Recent activity</h2><div id="logs" class="log">No events yet.</div></section>
</div></main><script>
const token='__TOKEN__';const startAfterSave=__START_AFTER_SAVE__;let state=null;let learning=false;
const $=id=>document.getElementById(id);const pct=n=>Math.round(n*100)+'%';
async function api(path,body){const options=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-DCS-Radio-Voice-Control-Token':token},body:JSON.stringify(body)};const response=await fetch(path,options);const value=await response.json();if(!response.ok)throw new Error(value.error||'Request failed');return value}
function option(select,value,label){const node=document.createElement('option');node.value=value;node.textContent=label;select.appendChild(node)}
function render(s){state=s;const c=s.config;$('microphone').innerHTML='';s.microphones.forEach(m=>option($('microphone'),m.device_id,m.name));if(c.microphone)$('microphone').value=c.microphone.device_id;$('score').min=s.score_range[0];$('score').max=s.score_range[1];$('score').value=c.matching.minimum_score;$('lead').min=s.lead_range[0];$('lead').max=s.lead_range[1];$('lead').value=c.matching.minimum_lead;$('audioCues').checked=c.feedback.audio_cues;$('cueVolume').min=s.cue_volume_range[0];$('cueVolume').max=s.cue_volume_range[1];$('cueVolume').value=c.feedback.cue_volume;$('model').innerHTML='';s.models.forEach(m=>option($('model'),m,m));$('model').value=c.stt.model;$('useGpu').checked=c.stt.use_gpu&&s.stt_compute==='cuda12';$('useGpu').disabled=s.stt_compute!=='cuda12';$('output').innerHTML='';option($('output'),'','Windows default');s.outputs.forEach(d=>option($('output'),d,d));$('output').value=c.audio.output_device||'';$('desktopShortcut').checked=startAfterSave?true:s.desktop_shortcut.exists;$('startWithWindows').checked=c.startup.start_with_windows;$('controllerState').textContent=`${s.controller.state}${s.controller.message?' — '+s.controller.message:''}`;values();const p=c.ptt;$('pttCurrent').textContent=p.mode==='hotas'?`${p.name} — button ${p.button}`:'Space keyboard';$('controllers').textContent=s.controllers.length?s.controllers.map(d=>`${d.name} (${d.button_count} buttons)`).join(' · '):'No SDL controllers detected.';$('paths').textContent=`Configuration: ${s.config_path} · Logs: ${s.log_path}`;renderLogs(s.events)}
function values(){$('scoreValue').textContent=pct(+$('score').value);$('leadValue').textContent=pct(+$('lead').value);$('cueValue').textContent=pct(+$('cueVolume').value)}
function renderLogs(events){const box=$('logs');box.innerHTML='';if(!events.length){box.textContent='No events yet.';return}events.slice().reverse().forEach(e=>{const row=document.createElement('div');row.textContent=`${e.timestamp||''}  ${e.event||''}  ${e.transcript||e.message||e.reason||''}`;box.appendChild(row)})}
async function load(){try{render(await api('/api/status'));$('save').textContent=startAfterSave?'Save configuration and start':'Save configuration'}catch(e){$('saveResult').textContent=e.message;$('saveResult').classList.add('error')}}
$('score').oninput=values;$('lead').oninput=values;$('cueVolume').oninput=values;
$('save').onclick=async()=>{try{const endpoint=startAfterSave?'/api/settings/start':'/api/settings';const s=await api(endpoint,{microphone_id:+$('microphone').value,minimum_score:+$('score').value,minimum_lead:+$('lead').value,model:$('model').value,use_gpu:$('useGpu').checked,output_device:$('output').value||null,audio_cues:$('audioCues').checked,cue_volume:+$('cueVolume').value,desktop_shortcut:$('desktopShortcut').checked,start_with_windows:$('startWithWindows').checked});render(s);$('saveResult').classList.remove('error');$('saveResult').textContent=startAfterSave?'Configuration saved. DCS Radio Voice Control is starting; you may close this page.':'Configuration saved.';$('save').disabled=startAfterSave}catch(e){$('saveResult').textContent=e.message;$('saveResult').classList.add('error')}};
$('micTest').onclick=async()=>{try{$('micResult').textContent='Speak normally for three seconds…';const r=await api('/api/microphone/test',{microphone_id:+$('microphone').value});$('micResult').textContent=`Average ${r.average_dbfs??'silence'} dBFS · peak ${r.peak_dbfs??'silence'} dBFS`}catch(e){$('micResult').textContent=e.message;$('micResult').classList.add('error')}};
$('learnPtt').onclick=async()=>{learning=true;try{$('pttCurrent').textContent='Scanning all controllers—press and release the desired button…';const r=await api('/api/hotas/learn',{});render(r.status);$('pttCurrent').textContent=`Saved ${r.binding.name} — button ${r.binding.button}. Press it again to test.`}catch(e){$('pttCurrent').textContent=e.message;$('pttCurrent').classList.add('error')}finally{learning=false}};
$('keyboardPtt').onclick=async()=>{try{render(await api('/api/hotas/keyboard',{}))}catch(e){$('pttCurrent').textContent=e.message}};
$('testAccepted').onclick=async()=>{try{await api('/api/cue/test',{outcome:'accepted',volume:+$('cueVolume').value,output_device:$('output').value||null})}catch(e){$('saveResult').textContent=e.message}};
$('testRejected').onclick=async()=>{try{await api('/api/cue/test',{outcome:'rejected',volume:+$('cueVolume').value,output_device:$('output').value||null})}catch(e){$('saveResult').textContent=e.message}};
$('testVoice').onclick=async()=>{try{await api('/api/voice/test',{output_device:$('output').value||null})}catch(e){$('saveResult').textContent=e.message}};
setInterval(async()=>{if(learning||!state||state.config.ptt.mode!=='hotas')return;try{const r=await api('/api/ptt-state');$('pttCurrent').classList.toggle('pressed',r.pressed);if(r.pressed)$('pttCurrent').textContent=`${r.label} — PRESSED`;else $('pttCurrent').textContent=`${r.label} — ready`}catch(e){}},120);
setInterval(async()=>{if(learning)return;try{const r=await api('/api/logs');renderLogs(r.events);$('controllerState').textContent=`${r.controller.state}${r.controller.message?' — '+r.controller.message:''}`}catch(e){}},5000);load();
</script></body></html>'''


if __name__ == "__main__":
    raise SystemExit(main())
