import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Check, Loader2, Map, Mic, MicOff, Navigation, Pause, Play, Send, Volume2, X,
} from 'lucide-react';
import { sendVoiceAudioQuery, sendVoiceTextQuery, updateProfile } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const LANGUAGE_OPTIONS = [
  { value: 'te-IN', label: 'Telugu' },
  { value: 'hi-IN', label: 'Hindi' },
  { value: 'en-IN', label: 'English' },
];

const SAFE_ACTIONS = new Set([
  'NAVIGATE',
  'OPEN_MAP',
  'START_BOUNDARY_DRAWING',
  'FOCUS_FIELD',
  'SHOW_SCORE',
  'SHOW_EARNINGS',
  'SHOW_DOCUMENT_STATUS',
]);

const SAFE_PROFILE_FIELDS = {
  name: 'name',
  village: 'village',
  district: 'district',
  state: 'state',
  'preferred language': 'preferred_language',
  upi: 'upi',
};

const ACTION_LABELS = {
  NAVIGATE: 'Open page',
  OPEN_MAP: 'Open map',
  START_BOUNDARY_DRAWING: 'Draw boundary',
  FOCUS_FIELD: 'Review fields',
  SHOW_SCORE: 'Show score',
  SHOW_EARNINGS: 'Show earnings',
  SHOW_DOCUMENT_STATUS: 'Show documents',
};

function pathForAction(action) {
  const path = action?.payload?.path;
  if (action?.type === 'NAVIGATE' && typeof path === 'string' && path.startsWith('/') && !path.startsWith('//')) return path;
  if (action?.type === 'OPEN_MAP' || action?.type === 'START_BOUNDARY_DRAWING') return '/farm-map';
  if (action?.type === 'SHOW_SCORE') return '/farm-analytics';
  if (action?.type === 'SHOW_EARNINGS') return '/wallet';
  if (action?.type === 'SHOW_DOCUMENT_STATUS') return '/farm-verification';
  return null;
}

export default function FarmerVoiceAssistant() {
  const navigate = useNavigate();
  const { role, refreshUser } = useAuth();
  const [language, setLanguage] = useState('te-IN');
  const [sessionId, setSessionId] = useState(null);
  const [text, setText] = useState('');
  const [transcript, setTranscript] = useState('');
  const [responseText, setResponseText] = useState('');
  const [actions, setActions] = useState([]);
  const [confirmation, setConfirmation] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [playing, setPlaying] = useState(false);
  const recorderRef = useRef(null);
  const speechRecognitionRef = useRef(null);
  const chunksRef = useRef([]);
  const audioRef = useRef(null);

  if (role !== 'farmer') return null;

  const applyResult = (data) => {
    if (!data?.success) {
      setError(data?.detail || data?.message || 'Voice assistant is unavailable.');
      return;
    }
    setSessionId(data.session_id || null);
    setTranscript(data.transcript || '');
    setResponseText(data.response_text || '');
    setActions((data.actions || []).filter((action) => SAFE_ACTIONS.has(action.type)));
    setConfirmation(data.confirmation || null);
    if (data.audio_base64) {
      audioRef.current = new Audio(`data:${data.audio_mime_type || 'audio/wav'};base64,${data.audio_base64}`);
      audioRef.current.onended = () => setPlaying(false);
    } else {
      audioRef.current = null;
    }
  };

  const askText = async (value = text) => {
    const prompt = value.trim();
    if (!prompt) return;
    setLoading(true);
    setError('');
    try {
      const data = await sendVoiceTextQuery({ text: prompt, language_code: language, session_id: sessionId });
      applyResult(data);
      setText('');
    } catch {
      setError('Could not reach the voice assistant.');
    } finally {
      setLoading(false);
    }
  };

  const stopRecording = () => {
    if (speechRecognitionRef.current) {
      speechRecognitionRef.current.stop();
      speechRecognitionRef.current = null;
    }
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop();
    }
    setRecording(false);
  };

  const startRecording = async () => {
    setError('');

    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognitionCtor) {
      try {
        const recognition = new SpeechRecognitionCtor();
        recognition.lang = language;
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.onstart = () => setRecording(true);
        recognition.onresult = (event) => {
          const results = Array.from(event.results || []);
          const finalResult = results[results.length - 1];
          const transcriptText = (finalResult?.[0]?.transcript || '').trim();
          if (transcriptText) {
            setText(transcriptText);
            setTranscript(transcriptText);
            if (finalResult?.isFinal) {
              recognition.stop();
              askText(transcriptText);
            }
          }
        };
        recognition.onerror = () => {
          setRecording(false);
          setError('Speech recognition is unavailable in this browser. Please use text input instead.');
        };
        recognition.onend = () => {
          setRecording(false);
          speechRecognitionRef.current = null;
        };
        speechRecognitionRef.current = recognition;
        recognition.start();
        return;
      } catch {
        setError('Could not start speech recognition. Falling back to audio upload.');
      }
    }

    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('Recording is not supported in this browser.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        setRecording(false);
        setLoading(true);
        try {
          const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
          const file = new File([blob], 'carbonx-voice.webm', { type: blob.type });
          const data = await sendVoiceAudioQuery({ file, language_code: language, session_id: sessionId });
          applyResult(data);
        } catch {
          setError('Could not process the recording.');
        } finally {
          setLoading(false);
        }
      };
      recorder.start();
      setRecording(true);
    } catch {
      setError('Microphone permission was not granted.');
    }
  };

  const playAudio = () => {
    if (!audioRef.current) return;
    setPlaying(true);
    audioRef.current.play().catch(() => setPlaying(false));
  };

  const runAction = (action) => {
    const path = pathForAction(action);
    if (path) navigate(path);
  };

  const safeProposals = confirmation?.proposed_fields || {};
  const profileUpdates = Object.entries(safeProposals).reduce((acc, [key, value]) => {
    const apiField = SAFE_PROFILE_FIELDS[key];
    if (apiField) acc[apiField] = value;
    return acc;
  }, {});

  const applySafeProfileUpdates = async () => {
    if (!Object.keys(profileUpdates).length) {
      setConfirmation(null);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await updateProfile(profileUpdates);
      if (!res.success) throw new Error(res.message);
      await refreshUser();
      setConfirmation(null);
    } catch {
      setError('Could not save the confirmed values.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="fixed right-4 bottom-20 md:bottom-4 z-50 w-[calc(100vw-2rem)] max-w-sm bg-white border border-forest-100 shadow-xl rounded-2xl overflow-hidden">
      <div className="px-4 py-3 border-b border-forest-100 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-8 h-8 rounded-xl bg-forest-800 text-white flex items-center justify-center shrink-0">
            <Volume2 size={16} />
          </div>
          <div className="min-w-0">
            <h2 className="text-xs font-black text-carbon-900 truncate">Farmer Voice Assistant</h2>
            <p className="text-[10px] text-carbon-500 truncate">Telugu, Hindi, English, mixed speech</p>
          </div>
        </div>
        <select
          value={language}
          onChange={(event) => setLanguage(event.target.value)}
          className="text-[11px] font-bold bg-forest-50 border border-forest-100 rounded-lg px-2 py-1.5 text-carbon-800 outline-none"
        >
          {LANGUAGE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </div>

      <div className="p-4 space-y-3">
        {error && <div className="text-[11px] text-rose-700 bg-rose-50 border border-rose-100 rounded-xl px-3 py-2">{error}</div>}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={recording ? stopRecording : startRecording}
            disabled={loading}
            className={`h-11 w-11 rounded-xl flex items-center justify-center text-white shrink-0 ${recording ? 'bg-rose-600' : 'bg-forest-800'} disabled:opacity-60`}
            title={recording ? 'Stop recording' : 'Start recording'}
          >
            {recording ? <MicOff size={18} /> : <Mic size={18} />}
          </button>
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => { if (event.key === 'Enter') askText(); }}
            placeholder="Ask about your farm"
            className="flex-1 min-w-0 h-11 px-3 rounded-xl border border-forest-100 bg-forest-50 text-sm text-carbon-800 outline-none focus:border-forest-500"
          />
          <button
            type="button"
            onClick={() => askText()}
            disabled={loading || !text.trim()}
            className="h-11 w-11 rounded-xl bg-carbon-800 text-white flex items-center justify-center disabled:opacity-50"
            title="Send"
          >
            {loading ? <Loader2 size={17} className="animate-spin" /> : <Send size={17} />}
          </button>
        </div>

        {(recording || loading) && (
          <div className="text-[11px] font-semibold text-carbon-500">
            {recording ? 'Listening...' : 'Processing securely...'}
          </div>
        )}

        {(transcript || responseText) && (
          <div className="space-y-2">
            {transcript && (
              <div className="rounded-xl bg-forest-50 border border-forest-100 px-3 py-2">
                <p className="text-[10px] uppercase font-bold text-carbon-400">Transcript</p>
                <p className="text-xs text-carbon-800 mt-1">{transcript}</p>
              </div>
            )}
            {responseText && (
              <div className="rounded-xl bg-white border border-forest-100 px-3 py-2">
                <div className="flex items-start gap-2">
                  <p className="flex-1 text-xs text-carbon-800 leading-relaxed">{responseText}</p>
                  {audioRef.current && (
                    <button
                      type="button"
                      onClick={playAudio}
                      disabled={playing}
                      className="w-8 h-8 rounded-lg bg-forest-100 text-forest-800 flex items-center justify-center shrink-0"
                      title="Play response"
                    >
                      {playing ? <Pause size={14} /> : <Play size={14} />}
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {actions.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {actions.map((action, index) => (
              <button
                key={`${action.type}-${index}`}
                type="button"
                onClick={() => runAction(action)}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-forest-800 text-white text-[11px] font-bold"
              >
                {action.type === 'OPEN_MAP' || action.type === 'START_BOUNDARY_DRAWING' ? <Map size={13} /> : <Navigation size={13} />}
                {ACTION_LABELS[action.type] || 'Open'}
              </button>
            ))}
          </div>
        )}

        {Object.keys(safeProposals).length > 0 && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
            <p className="text-[11px] font-black text-amber-900 mb-2">Confirm suggested values</p>
            <div className="space-y-1.5">
              {Object.entries(safeProposals).map(([key, value]) => (
                <div key={key} className="flex justify-between gap-3 text-[11px]">
                  <span className="font-bold text-amber-800">{key}</span>
                  <span className="text-carbon-700 text-right">{value}</span>
                </div>
              ))}
            </div>
            <div className="flex gap-2 mt-3">
              <button
                type="button"
                onClick={applySafeProfileUpdates}
                disabled={loading}
                className="flex-1 inline-flex items-center justify-center gap-1.5 py-2 rounded-xl bg-forest-800 text-white text-[11px] font-bold disabled:opacity-60"
              >
                <Check size={13} /> Apply safe fields
              </button>
              <button
                type="button"
                onClick={() => setConfirmation(null)}
                className="w-10 h-9 rounded-xl bg-white border border-amber-200 text-amber-800 flex items-center justify-center"
                title="Dismiss"
              >
                <X size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
