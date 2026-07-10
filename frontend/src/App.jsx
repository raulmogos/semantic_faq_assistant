import { useCallback, useEffect, useRef, useState } from "react";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import AddCommentOutlinedIcon from "@mui/icons-material/AddCommentOutlined";
import ChatBubbleOutlineOutlinedIcon from "@mui/icons-material/ChatBubbleOutlineOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import GppMaybeOutlinedIcon from "@mui/icons-material/GppMaybeOutlined";
import LogoutOutlinedIcon from "@mui/icons-material/LogoutOutlined";
import ManageSearchOutlinedIcon from "@mui/icons-material/ManageSearchOutlined";
import PersonOutlineOutlinedIcon from "@mui/icons-material/PersonOutlineOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import SupportAgentOutlinedIcon from "@mui/icons-material/SupportAgentOutlined";
import SyncOutlinedIcon from "@mui/icons-material/SyncOutlined";
import {
  Alert,
  AppBar,
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  Drawer,
  IconButton,
  Link,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Toolbar,
  Tooltip,
  Typography,
} from "@mui/material";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const DRAWER_WIDTH = 280;
const TOKEN_KEY = "fqa_token";
const USER_KEY = "fqa_user";

const SUGGESTIONS = [
  "How do I reset my password?",
  "Can I change my registered email address?",
  "How do I export my data?",
  "How do I enable two-factor authentication?",
  "What payment methods do you accept?",
];

const SOURCE_CONFIG = {
  vector_search: {
    label: "Knowledge Base",
    icon: ManageSearchOutlinedIcon,
    chipColor: "success",
    bgcolor: "#ecfdf5",
    borderColor: "#86efac",
    avatarBg: "success.main",
  },
  llm: {
    label: "AI Generated",
    icon: AutoAwesomeOutlinedIcon,
    chipColor: "secondary",
    bgcolor: "#f5f3ff",
    borderColor: "#c4b5fd",
    avatarBg: "secondary.main",
  },
  compliance: {
    label: "Out of Scope",
    icon: GppMaybeOutlinedIcon,
    chipColor: "warning",
    bgcolor: "#fffbeb",
    borderColor: "#fcd34d",
    avatarBg: "warning.main",
  },
};

// ---------------------------------------------------------------------------
// Auth helpers
// ---------------------------------------------------------------------------

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiFetch(path, options = {}) {
  return fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers ?? {}),
    },
  });
}

// ---------------------------------------------------------------------------
// AuthPage
// ---------------------------------------------------------------------------

function AuthPage({ onAuth }) {
  const [tab, setTab] = useState(0);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    const path = tab === 0 ? "/auth/login" : "/auth/register";
    try {
      const res = await fetch(`${API_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? "Something went wrong.");
        return;
      }
      localStorage.setItem(TOKEN_KEY, data.access_token);
      localStorage.setItem(USER_KEY, username);
      onAuth(username);
    } catch {
      setError("Could not reach the server.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        bgcolor: "background.default",
      }}
    >
      <Paper elevation={3} sx={{ width: 380, p: 4 }}>
        <Stack spacing={3}>
          <Stack alignItems="center" spacing={1}>
            <Avatar sx={{ bgcolor: "primary.main", width: 52, height: 52 }}>
              <SupportAgentOutlinedIcon />
            </Avatar>
            <Typography variant="h6" fontWeight={700}>
              Semantic FAQ Assistant
            </Typography>
          </Stack>

          <Tabs value={tab} onChange={(_, v) => { setTab(v); setError(""); }} centered>
            <Tab label="Login" />
            <Tab label="Register" />
          </Tabs>

          <Stack component="form" spacing={2} onSubmit={handleSubmit}>
            <TextField
              label="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              fullWidth
              autoFocus
              size="small"
            />
            <TextField
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              fullWidth
              size="small"
            />
            {error && <Alert severity="error">{error}</Alert>}
            <Button
              type="submit"
              variant="contained"
              fullWidth
              disabled={loading || !username || !password}
            >
              {loading ? <CircularProgress size={20} /> : tab === 0 ? "Login" : "Create Account"}
            </Button>
          </Stack>
        </Stack>
      </Paper>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Chat components
// ---------------------------------------------------------------------------

function AssistantMessage({ message }) {
  const config = SOURCE_CONFIG[message.source] ?? SOURCE_CONFIG.llm;
  const SourceIcon = config.icon;

  return (
    <Stack direction="row" spacing={1.5} alignItems="flex-start">
      <Avatar sx={{ width: 36, height: 36, bgcolor: config.avatarBg }}>
        <SourceIcon fontSize="small" />
      </Avatar>
      <Paper
        elevation={0}
        sx={{
          maxWidth: "78%",
          px: 2,
          py: 1.5,
          bgcolor: config.bgcolor,
          border: "1px solid",
          borderColor: config.borderColor,
        }}
      >
        <Stack spacing={1}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Chip size="small" color={config.chipColor} label={config.label} icon={<SourceIcon />} />
            {message.similarityScore != null && (
              <Typography variant="caption" color="text.secondary">
                Match {(message.similarityScore * 100).toFixed(0)}%
              </Typography>
            )}
          </Stack>
          <Typography variant="body1">{message.text}</Typography>
        </Stack>
      </Paper>
    </Stack>
  );
}

function SessionList({ sessions, activeSessionId, onSelect, onNewChat, onDelete, loading }) {
  return (
    <Drawer
      variant="permanent"
      sx={{
        width: DRAWER_WIDTH,
        flexShrink: 0,
        "& .MuiDrawer-paper": {
          width: DRAWER_WIDTH,
          boxSizing: "border-box",
          bgcolor: "grey.900",
          color: "common.white",
          borderRight: "none",
        },
      }}
    >
      <Toolbar sx={{ bgcolor: "primary.main" }}>
        <SupportAgentOutlinedIcon sx={{ mr: 1, color: "primary.contrastText" }} />
        <Typography variant="subtitle1" fontWeight={600} sx={{ flexGrow: 1, color: "primary.contrastText" }}>
          Conversations
        </Typography>
        <Tooltip title="New chat">
          <IconButton size="small" onClick={onNewChat} sx={{ color: "primary.contrastText" }}>
            <AddCommentOutlinedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Toolbar>

      <Divider sx={{ borderColor: "grey.700" }} />

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 4 }}>
          <CircularProgress size={24} sx={{ color: "grey.400" }} />
        </Box>
      ) : sessions.length === 0 ? (
        <Box sx={{ p: 2, textAlign: "center" }}>
          <Typography variant="body2" sx={{ color: "grey.500" }}>
            No past conversations
          </Typography>
        </Box>
      ) : (
        <List dense disablePadding sx={{ overflowY: "auto", flex: 1 }}>
          {sessions.map((session) => (
            <ListItemButton
              key={session.session_id}
              selected={session.session_id === activeSessionId}
              onClick={() => onSelect(session)}
              sx={{
                borderRadius: 1,
                mx: 0.5,
                my: 0.25,
                pr: 0.5,
                "&.Mui-selected": { bgcolor: "primary.dark", "&:hover": { bgcolor: "primary.dark" } },
                "&:hover": { bgcolor: "grey.800" },
                "&:hover .delete-btn": { opacity: 1 },
              }}
            >
              <ChatBubbleOutlineOutlinedIcon fontSize="small" sx={{ mr: 1.5, color: "grey.400", flexShrink: 0 }} />
              <ListItemText
                primary={session.preview ?? `Session ${session.session_id.slice(-8)}`}
                secondary={`${session.message_count} messages`}
                primaryTypographyProps={{ variant: "body2", noWrap: true, sx: { color: "common.white" } }}
                secondaryTypographyProps={{ variant: "caption", sx: { color: "grey.500" } }}
              />
              <Tooltip title="Delete session">
                <IconButton
                  className="delete-btn"
                  size="small"
                  onClick={(e) => { e.stopPropagation(); onDelete(session.session_id); }}
                  sx={{ opacity: 0, transition: "opacity 0.15s", color: "grey.400", flexShrink: 0, "&:hover": { color: "error.light" } }}
                >
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </ListItemButton>
          ))}
        </List>
      )}
    </Drawer>
  );
}

// ---------------------------------------------------------------------------
// Main app (authenticated)
// ---------------------------------------------------------------------------

function ChatApp({ username, onLogout }) {
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [embedTask, setEmbedTask] = useState(null);
  const [embedLoading, setEmbedLoading] = useState(false);
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const fetchSessions = useCallback(async () => {
    try {
      const res = await apiFetch("/sessions");
      if (res.status === 401) { onLogout(); return; }
      if (res.ok) setSessions(await res.json());
    } catch {
      // non-critical
    } finally {
      setSessionsLoading(false);
    }
  }, [onLogout]);

  useEffect(() => { fetchSessions(); }, [fetchSessions]);

  async function loadSession(session) {
    try {
      const res = await apiFetch(`/sessions/${session.session_id}`);
      if (!res.ok) return;
      const history = await res.json();
      setSessionId(session.session_id);
      setMessages(
        history.map((m) => ({
          role: m.role,
          text: m.content,
          source: m.source ?? (m.role === "assistant" ? "llm" : undefined),
          similarityScore: m.similarity_score ?? null,
        }))
      );
    } catch { /* ignore */ }
  }

  function startNewChat() {
    setSessionId(crypto.randomUUID());
    setMessages([]);
    setInput("");
  }

  async function deleteSession(id) {
    if (!window.confirm("Delete this conversation?")) return;
    try {
      await apiFetch(`/sessions/${id}`, { method: "DELETE" });
      if (id === sessionId) startNewChat();
      await fetchSessions();
    } catch { /* ignore */ }
  }

  async function triggerEmbed() {
    setEmbedLoading(true);
    setEmbedTask(null);
    try {
      const res = await apiFetch("/admin/embed", { method: "POST" });
      setEmbedTask(await res.json());
    } catch {
      setEmbedTask({ error: "Failed to reach the server." });
    } finally {
      setEmbedLoading(false);
    }
  }

  async function submitQuestion(question) {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: trimmedQuestion }]);
    setLoading(true);

    try {
      const response = await apiFetch("/ask-question", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, question: trimmedQuestion }),
      });

      if (response.status === 401) { onLogout(); return; }
      if (!response.ok) throw new Error("Request failed");

      const data = await response.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: data.answer, source: data.source, similarityScore: data.similarity_score },
      ]);
      fetchSessions();
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Sorry, I could not reach the server. Please try again in a moment.", source: "llm", similarityScore: null },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    submitQuestion(input);
  }

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <SessionList
        sessions={sessions}
        activeSessionId={sessionId}
        onSelect={loadSession}
        onNewChat={startNewChat}
        onDelete={deleteSession}
        loading={sessionsLoading}
      />

      <Box sx={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <AppBar position="static" elevation={0} sx={{ bgcolor: "primary.main", color: "primary.contrastText" }}>
          <Toolbar>
            <SupportAgentOutlinedIcon sx={{ mr: 1.5, color: "primary.contrastText" }} />
            <Box sx={{ flexGrow: 1 }}>
              <Typography variant="h6" component="h1" sx={{ color: "primary.contrastText" }}>
                Semantic FAQ Assistant
              </Typography>
              <Typography variant="caption" sx={{ opacity: 0.75, color: "primary.contrastText" }}>
                Powered by semantic search and AI
              </Typography>
            </Box>

            <Tooltip title="Re-indexes the knowledge base into the vector store">
              <span>
                <IconButton
                  onClick={triggerEmbed}
                  disabled={embedLoading}
                  sx={{ color: "primary.contrastText", borderRadius: 1, px: 1.5, gap: 0.75 }}
                >
                  {embedLoading
                    ? <CircularProgress size={16} sx={{ color: "primary.contrastText" }} />
                    : <SyncOutlinedIcon fontSize="small" />}
                  <Typography variant="button" sx={{ color: "primary.contrastText", fontSize: "0.75rem" }}>
                    {embedLoading ? "Rebuilding…" : "Rebuild Embeddings"}
                  </Typography>
                </IconButton>
              </span>
            </Tooltip>

            <Divider orientation="vertical" flexItem sx={{ mx: 1, borderColor: "rgba(255,255,255,0.3)" }} />

            <Stack direction="row" alignItems="center" spacing={0.5}>
              <PersonOutlineOutlinedIcon fontSize="small" sx={{ color: "primary.contrastText", opacity: 0.8 }} />
              <Typography variant="body2" sx={{ color: "primary.contrastText", opacity: 0.9 }}>
                {username}
              </Typography>
              <Tooltip title="Logout">
                <IconButton size="small" onClick={onLogout} sx={{ color: "primary.contrastText" }}>
                  <LogoutOutlinedIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          </Toolbar>
        </AppBar>

        <Collapse in={Boolean(embedTask)}>
          {embedTask?.error ? (
            <Alert severity="error" onClose={() => setEmbedTask(null)}>{embedTask.error}</Alert>
          ) : embedTask ? (
            <Alert severity="info" onClose={() => setEmbedTask(null)}>
              Embedding task queued — task ID: <strong>{embedTask.task_id}</strong>. Check status at{" "}
              <Link href={`${API_URL}/admin/embed/${embedTask.task_id}`} target="_blank" rel="noreferrer" sx={{ color: "blue" }}>
                {`${API_URL}/admin/embed/${embedTask.task_id}`}
              </Link>
            </Alert>
          ) : null}
        </Collapse>

        <Box sx={{ flex: 1, display: "flex", flexDirection: "column", p: 3, gap: 2, overflow: "hidden" }}>
          <Paper elevation={0} sx={{ flex: 1, p: 2, overflowY: "auto", border: "1px solid", borderColor: "divider" }}>
            {messages.length === 0 ? (
              <Stack alignItems="center" justifyContent="center" spacing={2} sx={{ height: "100%", py: 6, textAlign: "center" }}>
                <Avatar sx={{ width: 56, height: 56, bgcolor: "primary.main" }}>
                  <SmartToyOutlinedIcon />
                </Avatar>
                <Box>
                  <Typography variant="h6" gutterBottom>How can I help you today?</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Ask a question about your account, billing, security, or settings.
                  </Typography>
                </Box>
                <Stack spacing={1} alignItems="center">
                  <Stack direction="row" spacing={1}>
                    {SUGGESTIONS.slice(0, 3).map((s) => (
                      <Chip key={s} label={s} variant="outlined" clickable onClick={() => submitQuestion(s)} disabled={loading} />
                    ))}
                  </Stack>
                  <Stack direction="row" spacing={1}>
                    {SUGGESTIONS.slice(3).map((s) => (
                      <Chip key={s} label={s} variant="outlined" clickable onClick={() => submitQuestion(s)} disabled={loading} />
                    ))}
                  </Stack>
                </Stack>
              </Stack>
            ) : (
              <Stack spacing={2}>
                {messages.map((message, index) =>
                  message.role === "assistant" ? (
                    <AssistantMessage key={index} message={message} />
                  ) : (
                    <Stack key={index} direction="row" spacing={1.5} justifyContent="flex-end">
                      <Paper elevation={0} sx={{ maxWidth: "78%", px: 2, py: 1.5, bgcolor: "primary.main", color: "primary.contrastText" }}>
                        <Typography variant="body1">{message.text}</Typography>
                      </Paper>
                      <Avatar sx={{ width: 36, height: 36, bgcolor: "secondary.main" }}>
                        {username[0]?.toUpperCase()}
                      </Avatar>
                    </Stack>
                  )
                )}
                {loading && (
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <Avatar sx={{ width: 36, height: 36, bgcolor: "primary.main" }}>
                      <SmartToyOutlinedIcon fontSize="small" />
                    </Avatar>
                    <Paper elevation={0} sx={{ px: 2, py: 1.5, bgcolor: "grey.100", display: "flex", alignItems: "center", gap: 1 }}>
                      <CircularProgress size={16} />
                      <Typography variant="body2" color="text.secondary">Thinking...</Typography>
                    </Paper>
                  </Stack>
                )}
                <Box ref={chatEndRef} />
              </Stack>
            )}
          </Paper>

          <Paper component="form" elevation={0} onSubmit={handleSubmit} sx={{ p: 1.5, border: "1px solid", borderColor: "divider" }}>
            <Stack direction="row" spacing={1} alignItems="flex-end">
              <TextField
                fullWidth
                multiline
                maxRows={4}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask a question..."
                disabled={loading}
                variant="outlined"
                size="small"
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(e); } }}
              />
              <IconButton
                type="submit"
                color="primary"
                disabled={loading || !input.trim()}
                sx={{
                  bgcolor: "primary.main",
                  color: "primary.contrastText",
                  "&:hover": { bgcolor: "primary.dark" },
                  "&.Mui-disabled": { bgcolor: "action.disabledBackground", color: "action.disabled" },
                }}
              >
                <SendRoundedIcon />
              </IconButton>
            </Stack>
          </Paper>
        </Box>
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

export default function App() {
  const [username, setUsername] = useState(() => localStorage.getItem(USER_KEY) ?? null);
  const isAuthenticated = Boolean(getToken()) && Boolean(username);

  function handleAuth(name) {
    setUsername(name);
  }

  function handleLogout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setUsername(null);
  }

  if (!isAuthenticated) {
    return <AuthPage onAuth={handleAuth} />;
  }

  return <ChatApp username={username} onLogout={handleLogout} />;
}
