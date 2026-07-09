import { useCallback, useEffect, useRef, useState } from "react";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import AddCommentOutlinedIcon from "@mui/icons-material/AddCommentOutlined";
import ChatBubbleOutlineOutlinedIcon from "@mui/icons-material/ChatBubbleOutlineOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import GppMaybeOutlinedIcon from "@mui/icons-material/GppMaybeOutlined";
import ManageSearchOutlinedIcon from "@mui/icons-material/ManageSearchOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import SupportAgentOutlinedIcon from "@mui/icons-material/SupportAgentOutlined";
import {
  AppBar,
  Avatar,
  Box,
  Chip,
  CircularProgress,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
  TextField,
  Toolbar,
  Tooltip,
  Typography,
} from "@mui/material";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const DRAWER_WIDTH = 280;

const SUGGESTIONS = [
  "How do I reset my password?",
  "Can I change my registered email address?",
  "How do I export my data?",
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
            <Chip
              size="small"
              color={config.chipColor}
              label={config.label}
              icon={<SourceIcon />}
            />
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
                "&.Mui-selected": {
                  bgcolor: "primary.dark",
                  "&:hover": { bgcolor: "primary.dark" },
                },
                "&:hover": { bgcolor: "grey.800" },
                "&:hover .delete-btn": { opacity: 1 },
              }}
            >
              <ChatBubbleOutlineOutlinedIcon
                fontSize="small"
                sx={{ mr: 1.5, color: "grey.400", flexShrink: 0 }}
              />
              <ListItemText
                primary={session.preview ?? `Session ${session.session_id.slice(-8)}`}
                secondary={`${session.message_count} messages`}
                primaryTypographyProps={{
                  variant: "body2",
                  noWrap: true,
                  sx: { color: "common.white" },
                }}
                secondaryTypographyProps={{
                  variant: "caption",
                  sx: { color: "grey.500" },
                }}
              />
              <Tooltip title="Delete session">
                <IconButton
                  className="delete-btn"
                  size="small"
                  onClick={(e) => { e.stopPropagation(); onDelete(session.session_id); }}
                  sx={{
                    opacity: 0,
                    transition: "opacity 0.15s",
                    color: "grey.400",
                    flexShrink: 0,
                    "&:hover": { color: "error.light" },
                  }}
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

export default function App() {
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/sessions`);
      if (res.ok) setSessions(await res.json());
    } catch {
      // silently ignore — sessions list is non-critical
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  async function loadSession(session) {
    try {
      const res = await fetch(`${API_URL}/sessions/${session.session_id}`);
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
    } catch {
      // ignore
    }
  }

  function startNewChat() {
    setSessionId(crypto.randomUUID());
    setMessages([]);
    setInput("");
  }

  async function deleteSession(id) {
    if (!window.confirm("Delete this conversation?")) return;
    try {
      await fetch(`${API_URL}/sessions/${id}`, { method: "DELETE" });
      if (id === sessionId) startNewChat();
      await fetchSessions();
    } catch {
      // ignore
    }
  }

  async function submitQuestion(question) {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: trimmedQuestion }]);
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/ask-question`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, question: trimmedQuestion }),
      });

      if (!response.ok) throw new Error("Request failed");

      const data = await response.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: data.answer,
          source: data.source,
          similarityScore: data.similarity_score,
        },
      ]);
      fetchSessions();
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: "Sorry, I could not reach the server. Please try again in a moment.",
          source: "llm",
          similarityScore: null,
        },
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
            <Box>
              <Typography variant="h6" component="h1" sx={{ color: "primary.contrastText" }}>
                Semantic FAQ Assistant
              </Typography>
              <Typography variant="caption" sx={{ opacity: 0.75, color: "primary.contrastText" }}>
                Powered by semantic search and AI
              </Typography>
            </Box>
          </Toolbar>
        </AppBar>

        <Box sx={{ flex: 1, display: "flex", flexDirection: "column", p: 3, gap: 2, overflow: "hidden" }}>
          <Paper
            elevation={0}
            sx={{
              flex: 1,
              p: 2,
              overflowY: "auto",
              border: "1px solid",
              borderColor: "divider",
            }}
          >
            {messages.length === 0 ? (
              <Stack
                alignItems="center"
                justifyContent="center"
                spacing={2}
                sx={{ height: "100%", py: 6, textAlign: "center" }}
              >
                <Avatar sx={{ width: 56, height: 56, bgcolor: "primary.main" }}>
                  <SmartToyOutlinedIcon />
                </Avatar>
                <Box>
                  <Typography variant="h6" gutterBottom>
                    How can I help you today?
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Ask a question about your account, billing, security, or settings.
                  </Typography>
                </Box>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {SUGGESTIONS.map((suggestion) => (
                    <Chip
                      key={suggestion}
                      label={suggestion}
                      variant="outlined"
                      clickable
                      onClick={() => submitQuestion(suggestion)}
                      disabled={loading}
                    />
                  ))}
                </Stack>
              </Stack>
            ) : (
              <Stack spacing={2}>
                {messages.map((message, index) =>
                  message.role === "assistant" ? (
                    <AssistantMessage key={index} message={message} />
                  ) : (
                    <Stack key={index} direction="row" spacing={1.5} justifyContent="flex-end">
                      <Paper
                        elevation={0}
                        sx={{
                          maxWidth: "78%",
                          px: 2,
                          py: 1.5,
                          bgcolor: "primary.main",
                          color: "primary.contrastText",
                        }}
                      >
                        <Typography variant="body1">{message.text}</Typography>
                      </Paper>
                      <Avatar sx={{ width: 36, height: 36, bgcolor: "secondary.main" }}>
                        U
                      </Avatar>
                    </Stack>
                  )
                )}
                {loading && (
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <Avatar sx={{ width: 36, height: 36, bgcolor: "primary.main" }}>
                      <SmartToyOutlinedIcon fontSize="small" />
                    </Avatar>
                    <Paper
                      elevation={0}
                      sx={{
                        px: 2,
                        py: 1.5,
                        bgcolor: "grey.100",
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                      }}
                    >
                      <CircularProgress size={16} />
                      <Typography variant="body2" color="text.secondary">
                        Thinking...
                      </Typography>
                    </Paper>
                  </Stack>
                )}
                <Box ref={chatEndRef} />
              </Stack>
            )}
          </Paper>

          <Paper
            component="form"
            elevation={0}
            onSubmit={handleSubmit}
            sx={{ p: 1.5, border: "1px solid", borderColor: "divider" }}
          >
            <Stack direction="row" spacing={1} alignItems="flex-end">
              <TextField
                fullWidth
                multiline
                maxRows={4}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Ask a question..."
                disabled={loading}
                variant="outlined"
                size="small"
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    handleSubmit(event);
                  }
                }}
              />
              <IconButton
                type="submit"
                color="primary"
                disabled={loading || !input.trim()}
                sx={{
                  bgcolor: "primary.main",
                  color: "primary.contrastText",
                  "&:hover": { bgcolor: "primary.dark" },
                  "&.Mui-disabled": {
                    bgcolor: "action.disabledBackground",
                    color: "action.disabled",
                  },
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
