import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { ArrowUp, ChevronDown, RotateCcw, Sofa } from "lucide-react";

export const Route = createFileRoute("/")({
  component: App,
});

interface Message {
  role: "user" | "assistant";
  content: string;
  isError?: boolean;
}

interface PlacedItem {
  name: string;
  wall: "north" | "south" | "east" | "west" | null;
  corner: "north-east" | "north-west" | "south-east" | "south-west" | null;
  raw_hint: string;
}

interface RoomState {
  room_type?: string | null;
  width_cm?: number | null;
  length_cm?: number | null;
  existing_items?: string[];
  placed_items?: PlacedItem[];
  style_tags?: string[];
  style_text?: string | null;
  budget_total?: number | null;
  item_requests?: Array<{
    raw_phrase: string;
    max_price?: number | null;
    categories?: string[];
  }>;
}

interface Product {
  id: number;
  name: string;
  category: string;
  retailer: string;
  price: number | null;
  currency: string;
  width_cm: number | null;
  height_cm: number | null;
  depth_cm: number | null;
  diameter_cm: number | null;
  description: string | null;
  style_tags: string[];
  image_url: string | null;
  source_url: string;
  score: number;
}

const API_BASE = "http://localhost:8000/api/v1";

// ---------- Markdown ----------
function renderMarkdown(text: string) {
  const lines = text.split("\n");
  const blocks: React.ReactNode[] = [];
  let listBuffer: string[] = [];

  const flushList = (key: number) => {
    if (listBuffer.length === 0) return;
    blocks.push(
      <ul key={`ul-${key}`} className="list-disc pl-5 my-2 space-y-1">
        {listBuffer.map((item, i) => (
          <li key={i}>{renderInline(item)}</li>
        ))}
      </ul>,
    );
    listBuffer = [];
  };

  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("• ") || trimmed.startsWith("- ")) {
      listBuffer.push(trimmed.slice(2));
    } else {
      flushList(idx);
      if (trimmed === "") {
        blocks.push(<div key={`br-${idx}`} className="h-2" />);
      } else {
        blocks.push(
          <p key={`p-${idx}`} className="whitespace-pre-wrap">
            {renderInline(line)}
          </p>,
        );
      }
    }
  });
  flushList(lines.length);
  return <>{blocks}</>;
}

function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  const regex = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let lastIndex = 0;
  let match;
  let key = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      parts.push(
        <strong key={key++} className="font-semibold">
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      parts.push(
        <em key={key++} className="italic">
          {token.slice(1, -1)}
        </em>,
      );
    }
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return <>{parts}</>;
}

// ---------- Chat window ----------
function ChatWindow({
  messages,
  setMessages,
  sessionId,
  setSessionId,
  isLoading,
  setIsLoading,
  input,
  setInput,
  onStartOver,
  onApiResponse,
}: {
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  sessionId: string | null;
  setSessionId: React.Dispatch<React.SetStateAction<string | null>>;
  isLoading: boolean;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
  input: string;
  setInput: React.Dispatch<React.SetStateAction<string>>;
  onStartOver: () => void;
  onApiResponse: (data: {
    response: string;
    session_id: string;
    room_state?: RoomState;
    products?: Product[];
  }) => void;
}) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const lineHeight = 20;
    const maxHeight = lineHeight * 4 + 24;
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [input]);

  const send = async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setIsLoading(true);
    setTimeout(() => textareaRef.current?.focus(), 0);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      if (!res.ok) throw new Error("Request failed");
      const data = await res.json();
      if (data.session_id) setSessionId(data.session_id);
      onApiResponse(data);
      setMessages((m) => [...m, { role: "assistant", content: data.response }]);
    } catch {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: "Something went wrong — please try again.",
          isError: true,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const startOver = async () => {
    if (sessionId) {
      try {
        await fetch(`${API_BASE}/session/${sessionId}`, { method: "DELETE" });
      } catch {
        // ignore
      }
    }
    onStartOver();
    setTimeout(() => textareaRef.current?.focus(), 0);
  };

  const canSend = input.trim().length > 0 && !isLoading;

  return (
    <div className="flex h-screen w-[50vw] flex-col" style={{ backgroundColor: "#faf8f5" }}>
      {/* Header */}
      <div
        className="flex items-center justify-between"
        style={{
          padding: "16px 24px",
          borderBottom: "1px solid #e8e0d5",
          background: "linear-gradient(180deg, #ffffff 0%, #faf8f5 100%)",
        }}
      >
        <h1 style={{ fontSize: 20, fontWeight: 500, color: "#1a1208" }}>
          <span style={{ color: "#c4714a" }}>D</span>eco
        </h1>
        <button
          onClick={startOver}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 transition-colors hover:bg-black/5"
          style={{ color: "#c4714a", fontSize: 13 }}
        >
          <RotateCcw size={14} color="#c4714a" />
          Start over
        </button>
      </div>

      {/* Messages */}
      <div
        className="flex-1 overflow-y-auto"
        style={{ padding: "16px 24px", backgroundColor: "#faf8f5" }}
      >
        {messages.length === 0 && !isLoading ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <Sofa size={32} color="#c4b8a8" />
            <p className="mt-3" style={{ color: "#8c7b6e", fontSize: 14 }}>
              Describe your room and I'll recommend the perfect pieces.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {messages.map((msg, i) => (
              <MessageBubble key={i} message={msg} />
            ))}
            {isLoading && <LoadingBubble />}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div
        style={{
          backgroundColor: "#f5f2ee",
          borderTop: "1px solid #e8e0d5",
          padding: "16px 24px",
        }}
      >
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe your room or ask for recommendations…"
            rows={1}
            autoFocus
            className="deco-textarea flex-1 resize-none rounded-xl px-3 py-2.5 outline-none"
            style={{
              backgroundColor: "#ffffff",
              border: "1px solid #e8e0d5",
              fontSize: 14,
              lineHeight: "20px",
              minHeight: 44,
              color: "#1a1208",
            }}
          />
          <button
            onClick={send}
            disabled={!canSend}
            aria-label="Send message"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-opacity"
            style={{
              backgroundColor: "#c4714a",
              opacity: canSend ? 1 : 0.3,
              cursor: canSend ? "pointer" : "not-allowed",
            }}
          >
            <ArrowUp size={18} color="#ffffff" />
          </button>
        </div>
        <style>{`
          .deco-textarea::placeholder { color: #b5a89a; }
          .deco-textarea:focus {
            border-color: #c4714a !important;
            box-shadow: 0 0 0 3px rgba(196, 113, 74, 0.15);
          }
        `}</style>
      </div>
    </div>
  );
}


function MessageBubble({ message }: { message: Message }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div
          style={{
            backgroundColor: "#f0ebe4",
            border: "1px solid #e8e0d5",
            color: "#1a1208",
            maxWidth: "75%",
            borderRadius: "16px 16px 4px 16px",
            padding: "12px 16px",
            fontSize: 14,
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div
        style={{
          maxWidth: "85%",
          padding: "4px 0",
          fontSize: 14,
          lineHeight: 1.5,
          color: message.isError ? "#ef4444" : "#1a1208",
          wordBreak: "break-word",
        }}
      >
        {renderMarkdown(message.content)}
      </div>
    </div>
  );
}


function LoadingBubble() {
  return (
    <div className="flex justify-start">
      <div
        style={{ maxWidth: "85%", padding: "4px 0", color: "#c4714a" }}
        className="flex items-center gap-1"
      >
        <span className="deco-dot" style={{ animationDelay: "0ms" }}>
          •
        </span>
        <span className="deco-dot" style={{ animationDelay: "200ms" }}>
          •
        </span>
        <span className="deco-dot" style={{ animationDelay: "400ms" }}>
          •
        </span>
        <style>{`
          .deco-dot { display: inline-block; animation: decoPulse 1.2s ease-in-out infinite; font-size: 20px; line-height: 1; }
          @keyframes decoPulse { 0%,100% { opacity: 0.2; } 50% { opacity: 1; } }
        `}</style>
      </div>
    </div>
  );
}

// ---------- Collapsible section ----------
function Section({
  title,
  open,
  onToggle,
  children,
  style,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <div className="flex flex-col overflow-hidden" style={style}>
      <button
        onClick={onToggle}
        className="flex shrink-0 items-center justify-between"
        style={{
          height: 44,
          padding: "0 20px",
          backgroundColor: "#ffffff",
          borderBottom: "1px solid #e8e0d5",
        }}
      >
        <span
          style={{
            color: "#8c7b6e",
            fontSize: 12,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          {title}
        </span>
        <ChevronDown
          size={16}
          color="#b5a89a"
          style={{
            transform: open ? "rotate(0deg)" : "rotate(-90deg)",
            transition: "transform 200ms ease",
          }}
        />

      </button>
      {open && <div className="flex-1 overflow-hidden">{children}</div>}
    </div>
  );
}

// ---------- Room sketch ----------
const FURNITURE_SIZES: Record<string, [number, number]> = {
  "queen bed": [160, 200],
  "king bed": [193, 203],
  "single bed": [90, 190],
  bed: [160, 200],
  sofa: [220, 90],
  armchair: [80, 80],
  "coffee table": [110, 60],
  desk: [120, 60],
  "wooden desk": [120, 60],
  "dining table": [150, 90],
  wardrobe: [120, 60],
  bookshelf: [80, 30],
  "tv unit": [150, 45],
  dresser: [100, 45],
};

function getSize(name: string): [number, number] {
  const key = name.toLowerCase().trim();
  if (FURNITURE_SIZES[key]) return FURNITURE_SIZES[key];
  for (const [k, v] of Object.entries(FURNITURE_SIZES)) {
    if (key.includes(k)) return v;
  }
  return [60, 60];
}

function FurnitureSymbol({
  name,
  x,
  y,
  w,
  h,
  suggested,
}: {
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
  suggested?: boolean;
}) {
  const key = name.toLowerCase();
  const fill = suggested ? "#edf5ed" : "#e8e0d5";
  const stroke = suggested ? "#5a8a5a" : "#8c7b6e";
  const labelColor = suggested ? "#4a7a4a" : "#5c4f45";
  const strokeDash = suggested ? "3,3" : undefined;


  const base = (
    <rect
      x={x}
      y={y}
      width={w}
      height={h}
      fill={fill}
      stroke={stroke}
      strokeWidth={1}
      strokeDasharray={strokeDash}
      rx={2}
    />
  );

  let detail: React.ReactNode = null;

  if (key.includes("bed")) {
    detail = (
      <>
        <rect
          x={x + 4}
          y={y + 2}
          width={w - 8}
          height={h * 0.25 - 2}
          fill="#f5f0e8"
          opacity={0.85}
          rx={1}
        />
        <line
          x1={x + 4}
          y1={y + h * 0.55}
          x2={x + w - 4}
          y2={y + h * 0.55}
          stroke="#9ca3af"
          strokeWidth={0.7}
        />
        <line
          x1={x + 4}
          y1={y + h * 0.7}
          x2={x + w - 4}
          y2={y + h * 0.7}
          stroke="#9ca3af"
          strokeWidth={0.7}
        />
      </>
    );
  } else if (key.includes("sofa")) {
    detail = (
      <>
        <rect x={x} y={y} width={w} height={h * 0.15} fill="#d4c4b0" opacity={0.5} />
        <rect x={x} y={y} width={h * 0.25} height={h} fill="#d4c4b0" opacity={0.5} />
        <rect x={x + w - h * 0.25} y={y} width={h * 0.25} height={h} fill="#d4c4b0" opacity={0.5} />
      </>
    );
  } else if (key.includes("armchair")) {
    detail = (
      <>
        <rect x={x} y={y} width={w} height={h * 0.2} fill="#d4c4b0" opacity={0.4} />
        <rect x={x} y={y} width={w * 0.18} height={h} fill="#d4c4b0" opacity={0.4} />
        <rect x={x + w - w * 0.18} y={y} width={w * 0.18} height={h} fill="#d4c4b0" opacity={0.4} />
      </>
    );
  } else if (key.includes("desk")) {
    detail = (
      <>
        <rect x={x} y={y} width={w} height={h * 0.2} fill="#d4c4b0" opacity={0.4} />
        <rect
          x={x + w - w * 0.25}
          y={y}
          width={w * 0.25}
          height={h}
          fill="#d4c4b0"
          opacity={0.3}
        />
      </>
    );
  } else if (key.includes("tv")) {
    detail = (
      <rect
        x={x + w * 0.35}
        y={y + h * 0.25}
        width={w * 0.3}
        height={h * 0.5}
        fill="#1a1a2e"
      />
    );
  } else if (key.includes("coffee")) {
    detail = (
      <rect
        x={x + 4}
        y={y + 4}
        width={w - 8}
        height={h - 8}
        fill="none"
        stroke={stroke}
        strokeWidth={0.5}
        opacity={0.7}
      />
    );
  } else if (key.includes("wardrobe")) {
    detail = (
      <>
        <line
          x1={x + w / 2}
          y1={y}
          x2={x + w / 2}
          y2={y + h}
          stroke={stroke}
          strokeWidth={0.7}
        />
        <circle cx={x + w / 2 - 3} cy={y + h / 2} r={1.5} fill={stroke} />
        <circle cx={x + w / 2 + 3} cy={y + h / 2} r={1.5} fill={stroke} />
      </>
    );
  } else if (key.includes("bookshelf")) {
    detail = (
      <>
        <line
          x1={x + w * 0.25}
          y1={y}
          x2={x + w * 0.25}
          y2={y + h}
          stroke={stroke}
          strokeWidth={0.6}
        />
        <line
          x1={x + w * 0.5}
          y1={y}
          x2={x + w * 0.5}
          y2={y + h}
          stroke={stroke}
          strokeWidth={0.6}
        />
        <line
          x1={x + w * 0.75}
          y1={y}
          x2={x + w * 0.75}
          y2={y + h}
          stroke={stroke}
          strokeWidth={0.6}
        />
      </>
    );
  } else if (key.includes("dining")) {
    const chairs: React.ReactNode[] = [];
    const chairSize = 8;
    for (let i = 0; i < 3; i++) {
      const cx = x + (w / 4) * (i + 1) - chairSize / 2;
      chairs.push(
        <rect
          key={`ct-${i}`}
          x={cx}
          y={y - chairSize - 2}
          width={chairSize}
          height={chairSize}
          fill={fill}
          stroke={stroke}
          strokeWidth={0.5}
        />,
      );
      chairs.push(
        <rect
          key={`cb-${i}`}
          x={cx}
          y={y + h + 2}
          width={chairSize}
          height={chairSize}
          fill={fill}
          stroke={stroke}
          strokeWidth={0.5}
        />,
      );
    }
    detail = <>{chairs}</>;
  }

  return (
    <g>
      {base}
      {detail}
      <text
        x={x + w / 2}
        y={y + h / 2 + 3}
        textAnchor="middle"
        fontSize={9}
        fill={labelColor}
        style={{ pointerEvents: "none" }}
      >
        {name.length > 14 ? name.slice(0, 12) + "…" : name}
      </text>
    </g>
  );
}

function RoomSketch({ roomState }: { roomState: RoomState | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 400, h: 300 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setSize({ w: el.clientWidth, h: el.clientHeight });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const hasRoom = roomState && roomState.width_cm && roomState.length_cm;

  return (
    <div
      ref={containerRef}
      className="h-full w-full"
      style={{ backgroundColor: "#faf8f5", padding: 16 }}
    >
      {!hasRoom ? (
        <div className="flex h-full items-center justify-center text-center">
          <p style={{ color: "#b5a89a", fontSize: 13, maxWidth: 260 }}>
            Start describing your room to see the sketch appear here.
          </p>

        </div>
      ) : (
        <SketchSVG
          roomState={roomState!}
          canvasW={Math.max(size.w - 32, 100)}
          canvasH={Math.max(size.h - 32, 100)}
        />
      )}
    </div>
  );
}

function SketchSVG({
  roomState,
  canvasW,
  canvasH,
}: {
  roomState: RoomState;
  canvasW: number;
  canvasH: number;
}) {
  const width_cm = roomState.width_cm || 400;
  const length_cm = roomState.length_cm || 300;
  const scale = Math.min((canvasW - 40) / width_cm, (canvasH - 40) / length_cm);
  const scaledW = width_cm * scale;
  const scaledH = length_cm * scale;
  const offsetX = (canvasW - scaledW) / 2;
  const offsetY = (canvasH - scaledH) / 2;
  const margin = 20;

  const isWindow = (n: string) => n.toLowerCase().includes("window");

  const placedAll = roomState.placed_items || [];
  const existingAll = roomState.existing_items || [];
  const placed = placedAll.filter((p) => !isWindow(p.name));
  const existing = existingAll.filter((n) => !isWindow(n));
  const placedNames = new Set(placed.map((p) => p.name.toLowerCase()));

  // Collect windows and their walls
  type WallDir = "north" | "south" | "east" | "west";
  const windowWalls: WallDir[] = [];
  for (const p of placedAll) {
    if (!isWindow(p.name)) continue;
    if (p.wall) windowWalls.push(p.wall);
    else windowWalls.push("south");
  }
  for (const n of existingAll) {
    if (!isWindow(n)) continue;
    // if there's no placed_items match for this window, default to south
    const hasPlaced = placedAll.some(
      (p) => isWindow(p.name) && p.name.toLowerCase() === n.toLowerCase(),
    );
    if (!hasPlaced) windowWalls.push("south");
  }

  interface Rect { x: number; y: number; w: number; h: number }
  const occupiedRects: Rect[] = [];
  const items: React.ReactNode[] = [];
  let itemKey = 0;

  const wallPointers = { north: margin, south: margin, east: margin, west: margin };

  const pushItem = (name: string, x: number, y: number, w: number, h: number, suggested = false) => {
    occupiedRects.push({ x, y, w, h });
    items.push(
      <FurnitureSymbol key={itemKey++} name={name} x={x} y={y} w={w} h={h} suggested={suggested} />,
    );
  };

  // Corner-placed
  for (const p of placed) {
    if (!p.corner) continue;
    const [w, d] = getSize(p.name);
    const iw = w * scale;
    const id = d * scale;
    let ix = offsetX + margin;
    let iy = offsetY + margin;
    if (p.corner === "north-east") ix = offsetX + scaledW - iw - margin;
    if (p.corner === "south-west") iy = offsetY + scaledH - id - margin;
    if (p.corner === "south-east") {
      ix = offsetX + scaledW - iw - margin;
      iy = offsetY + scaledH - id - margin;
    }
    pushItem(p.name, ix, iy, iw, id);
  }

  // Wall-placed
  for (const p of placed) {
    if (!p.wall || p.corner) continue;
    const [w, d] = getSize(p.name);
    const iw = w * scale;
    const id = d * scale;
    let ix = offsetX + margin;
    let iy = offsetY + margin;
    if (p.wall === "north") {
      ix = offsetX + wallPointers.north;
      iy = offsetY + margin;
      wallPointers.north += iw + 10;
    } else if (p.wall === "south") {
      ix = offsetX + wallPointers.south;
      iy = offsetY + scaledH - id - margin;
      wallPointers.south += iw + 10;
    } else if (p.wall === "west") {
      ix = offsetX + margin;
      iy = offsetY + wallPointers.west;
      wallPointers.west += id + 10;
    } else if (p.wall === "east") {
      ix = offsetX + scaledW - iw - margin;
      iy = offsetY + wallPointers.east;
      wallPointers.east += id + 10;
    }
    pushItem(p.name, ix, iy, iw, id);
  }

  // Remaining existing items — clockwise fallback (N -> E -> S -> W), advance until wall full
  const wallsOrder: WallDir[] = ["north", "east", "south", "west"];
  let wallIdx = 0;
  for (const name of existing) {
    if (placedNames.has(name.toLowerCase())) continue;
    const [w, d] = getSize(name);
    const iw = w * scale;
    const id = d * scale;

    let placedOk = false;
    for (let attempt = 0; attempt < 4 && !placedOk; attempt++) {
      const wall = wallsOrder[wallIdx % 4];
      const along = wall === "north" || wall === "south" ? iw : id;
      const wallLen = wall === "north" || wall === "south" ? scaledW : scaledH;
      if (wallPointers[wall] + along + margin > wallLen) {
        wallIdx++;
        continue;
      }
      let ix = offsetX + margin;
      let iy = offsetY + margin;
      if (wall === "north") {
        ix = offsetX + wallPointers.north;
        iy = offsetY + margin;
        wallPointers.north += iw + 10;
      } else if (wall === "south") {
        ix = offsetX + wallPointers.south;
        iy = offsetY + scaledH - id - margin;
        wallPointers.south += iw + 10;
      } else if (wall === "west") {
        ix = offsetX + margin;
        iy = offsetY + wallPointers.west;
        wallPointers.west += id + 10;
      } else {
        ix = offsetX + scaledW - iw - margin;
        iy = offsetY + wallPointers.east;
        wallPointers.east += id + 10;
      }
      pushItem(name, ix, iy, iw, id);
      wallIdx++;
      placedOk = true;
    }
    if (!placedOk) {
      // last resort: center
      pushItem(name, offsetX + scaledW / 2 - iw / 2, offsetY + scaledH / 2 - id / 2, iw, id);
    }
  }

  // Suggested items — grid search avoiding occupied rects
  const requests = roomState.item_requests || [];
  const cell = 20;
  const rectsOverlap = (a: Rect, b: Rect) =>
    a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  const centerX = offsetX + scaledW / 2;
  const centerY = offsetY + scaledH / 2;

  let suggestIdx = 0;
  for (const r of requests) {
    const [w, d] = getSize(r.raw_phrase);
    const iw = w * scale;
    const id = d * scale;

    let best: { x: number; y: number; score: number } | null = null;
    for (let cy = offsetY + margin; cy + id <= offsetY + scaledH - margin; cy += cell) {
      for (let cx = offsetX + margin; cx + iw <= offsetX + scaledW - margin; cx += cell) {
        const cand: Rect = { x: cx, y: cy, w: iw, h: id };
        let overlap = false;
        for (const o of occupiedRects) {
          if (rectsOverlap(cand, o)) { overlap = true; break; }
        }
        if (overlap) continue;
        const dx = cx + iw / 2 - centerX;
        const dy = cy + id / 2 - centerY;
        const score = -Math.sqrt(dx * dx + dy * dy);
        if (!best || score > best.score) best = { x: cx, y: cy, score };
      }
    }

    let ix: number;
    let iy: number;
    if (best) {
      ix = best.x;
      iy = best.y;
    } else {
      const off = suggestIdx * 8;
      ix = centerX - iw / 2 + off;
      iy = centerY - id / 2 + off;
    }
    pushItem(r.raw_phrase, ix, iy, iw, id, true);
    suggestIdx++;
  }

  // Wall segments (with window gaps)
  const wallStroke = "#1a1208";
  const wallSW = 3;
  const windowEls: React.ReactNode[] = [];
  const wallEls: React.ReactNode[] = [];
  const windowsByWall: Record<WallDir, boolean> = {
    north: windowWalls.includes("north"),
    south: windowWalls.includes("south"),
    east: windowWalls.includes("east"),
    west: windowWalls.includes("west"),
  };

  const drawHWall = (y: number, side: "north" | "south") => {
    const x1 = offsetX;
    const x2 = offsetX + scaledW;
    if (windowsByWall[side]) {
      const wc = offsetX + scaledW / 2;
      const ws = wc - 40;
      const we = wc + 40;
      wallEls.push(<line key={`w-${side}-1`} x1={x1} y1={y} x2={ws} y2={y} stroke={wallStroke} strokeWidth={wallSW} />);
      wallEls.push(<line key={`w-${side}-2`} x1={we} y1={y} x2={x2} y2={y} stroke={wallStroke} strokeWidth={wallSW} />);
      windowEls.push(<line key={`g-${side}-1`} x1={ws} y1={y - 2} x2={we} y2={y - 2} stroke="#a0c4d8" strokeWidth={1.5} />);
      windowEls.push(<line key={`g-${side}-2`} x1={ws} y1={y + 2} x2={we} y2={y + 2} stroke="#a0c4d8" strokeWidth={1.5} />);
      const ly = side === "north" ? y - 6 : y + 12;
      windowEls.push(<text key={`g-${side}-t`} x={wc} y={ly} textAnchor="middle" fontSize={8} fill="#8c7b6e">W</text>);
    } else {
      wallEls.push(<line key={`w-${side}`} x1={x1} y1={y} x2={x2} y2={y} stroke={wallStroke} strokeWidth={wallSW} />);
    }
  };
  const drawVWall = (x: number, side: "east" | "west") => {
    const y1 = offsetY;
    const y2 = offsetY + scaledH;
    if (windowsByWall[side]) {
      const wc = offsetY + scaledH / 2;
      const ws = wc - 40;
      const we = wc + 40;
      wallEls.push(<line key={`w-${side}-1`} x1={x} y1={y1} x2={x} y2={ws} stroke={wallStroke} strokeWidth={wallSW} />);
      wallEls.push(<line key={`w-${side}-2`} x1={x} y1={we} x2={x} y2={y2} stroke={wallStroke} strokeWidth={wallSW} />);
      windowEls.push(<line key={`g-${side}-1`} x1={x - 2} y1={ws} x2={x - 2} y2={we} stroke="#a0c4d8" strokeWidth={1.5} />);
      windowEls.push(<line key={`g-${side}-2`} x1={x + 2} y1={ws} x2={x + 2} y2={we} stroke="#a0c4d8" strokeWidth={1.5} />);
      const lx = side === "west" ? x - 8 : x + 8;
      windowEls.push(<text key={`g-${side}-t`} x={lx} y={wc + 3} textAnchor="middle" fontSize={8} fill="#8c7b6e">W</text>);
    } else {
      wallEls.push(<line key={`w-${side}`} x1={x} y1={y1} x2={x} y2={y2} stroke={wallStroke} strokeWidth={wallSW} />);
    }
  };
  drawHWall(offsetY, "north");
  drawHWall(offsetY + scaledH, "south");
  drawVWall(offsetX, "west");
  drawVWall(offsetX + scaledW, "east");

  return (
    <svg width={canvasW} height={canvasH} style={{ display: "block" }}>
      {roomState.room_type && (
        <text
          x={offsetX + scaledW / 2}
          y={offsetY - 6}
          textAnchor="middle"
          fontSize={11}
          fill="#8c7b6e"
        >
          {roomState.room_type}
        </text>
      )}
      {wallEls}
      {windowEls}
      {items}
      <text x={8} y={canvasH - 8} fontSize={10} fill="#b5a89a">
        {width_cm} × {length_cm} cm
      </text>
      <g transform={`translate(${canvasW - 140}, ${canvasH - 20})`}>
        <rect x={0} y={0} width={10} height={10} fill="#e8e0d5" stroke="#8c7b6e" strokeWidth={0.7} />
        <text x={14} y={9} fontSize={10} fill="#8c7b6e">
          existing
        </text>
        <rect
          x={62}
          y={0}
          width={10}
          height={10}
          fill="#edf5ed"
          stroke="#5a8a5a"
          strokeWidth={0.7}
          strokeDasharray="2,2"
        />
        <text x={76} y={9} fontSize={10} fill="#8c7b6e">
          suggested
        </text>
      </g>

    </svg>
  );
}

// ---------- Recommendations ----------
function Recommendations({ products, loading }: { products: Product[]; loading: boolean }) {
  return (
    <div
      className="h-full overflow-y-auto"
      style={{ backgroundColor: "#faf8f5", padding: "12px 16px" }}
    >
      {loading && products.length === 0 ? (
        <div className="flex flex-col gap-2.5">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : products.length === 0 ? (
        <div className="flex h-full items-center justify-center text-center">
          <p style={{ color: "#b5a89a", fontSize: 13, maxWidth: 280 }}>
            Recommendations will appear here after you describe what you're looking for.
          </p>
        </div>

      ) : (
        <div className="flex flex-col gap-2.5">
          {products.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      )}
    </div>
  );
}

function ProductCard({ product }: { product: Product }) {
  return (
    <a
      href={product.source_url}
      target="_blank"
      rel="noreferrer noopener"
      className="deco-card flex gap-3"
      style={{
        backgroundColor: "#ffffff",
        border: "1px solid #e8e0d5",
        borderRadius: 10,
        padding: 12,
        textDecoration: "none",
        transition: "border-color 180ms ease",
      }}
    >
      <div
        className="flex shrink-0 items-center justify-center overflow-hidden"
        style={{ width: 72, height: 72, backgroundColor: "#f0ebe4", borderRadius: 6 }}
      >
        {product.image_url ? (
          <img src={product.image_url} alt={product.name} className="h-full w-full object-cover" />
        ) : (
          <Sofa size={24} color="#c4b8a8" />
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div
          style={{
            color: "#1a1208",
            fontSize: 13,
            fontWeight: 500,
            lineHeight: 1.35,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {product.name}
        </div>
        <div style={{ color: "#8c7b6e", fontSize: 11 }}>{product.retailer}</div>
        <div className="mt-auto flex items-center justify-between gap-2">
          <div
            style={{
              color: product.price != null ? "#c4714a" : "#b5a89a",
              fontSize: 13,
              fontWeight: 700,
            }}
          >
            {product.price != null
              ? `${product.currency || ""}${product.price}`.trim()
              : "Price unavailable"}
          </div>
          <div className="flex gap-1">
            {product.style_tags.slice(0, 2).map((t) => (
              <span
                key={t}
                style={{
                  backgroundColor: "#f0ebe4",
                  color: "#8c7b6e",
                  fontSize: 10,
                  padding: "2px 6px",
                  borderRadius: 999,
                }}
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      </div>
      <style>{`.deco-card:hover { border-color: #c4714a !important; }`}</style>
    </a>
  );
}


function SkeletonCard() {
  return (
    <div
      style={{
        backgroundColor: "#ffffff",
        border: "1px solid #e8e0d5",
        borderRadius: 10,
        padding: 12,
        display: "flex",
        gap: 12,
      }}
    >
      <div className="deco-shimmer" style={{ width: 72, height: 72, borderRadius: 6 }} />
      <div className="flex flex-1 flex-col gap-2 py-1">
        <div className="deco-shimmer" style={{ height: 12, width: "80%", borderRadius: 4 }} />
        <div className="deco-shimmer" style={{ height: 10, width: "40%", borderRadius: 4 }} />
        <div className="deco-shimmer mt-auto" style={{ height: 12, width: "30%", borderRadius: 4 }} />
      </div>
      <style>{`
        .deco-shimmer {
          background: linear-gradient(90deg, #f0ebe4 0%, #e8e0d5 50%, #f0ebe4 100%);
          background-size: 200% 100%;
          animation: decoShimmer 1.4s ease-in-out infinite;
        }
        @keyframes decoShimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>

    </div>
  );
}

// ---------- Right panel ----------
function RightPanel({
  roomState,
  products,
  loading,
}: {
  roomState: RoomState | null;
  products: Product[];
  loading: boolean;
}) {
  const [sketchOpen, setSketchOpen] = useState(true);
  const [recsOpen, setRecsOpen] = useState(true);

  const sketchFlex = sketchOpen ? (recsOpen ? 45 : 100) : 0;
  const recsFlex = recsOpen ? (sketchOpen ? 55 : 100) : 0;

  return (
    <div className="flex h-screen w-[50vw] flex-col" style={{ backgroundColor: "#f5f2ee", borderLeft: "1px solid #e8e0d5" }}>
      <Section
        title="Room sketch"
        open={sketchOpen}
        onToggle={() => setSketchOpen((v) => !v)}
        style={{
          flex: sketchOpen ? `${sketchFlex} 1 0` : "0 0 44px",
          minHeight: 44,
        }}
      >
        <RoomSketch roomState={roomState} />
      </Section>
      <Section
        title="Recommendations"
        open={recsOpen}
        onToggle={() => setRecsOpen((v) => !v)}
        style={{
          flex: recsOpen ? `${recsFlex} 1 0` : "0 0 44px",
          minHeight: 44,
        }}
      >
        <Recommendations products={products} loading={loading} />
      </Section>
    </div>
  );
}

// ---------- App ----------
function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [input, setInput] = useState("");
  const [roomState, setRoomState] = useState<RoomState | null>(null);
  const [products, setProducts] = useState<Product[]>([]);

  const handleApiResponse = (data: {
    response: string;
    session_id: string;
    room_state?: RoomState;
    products?: Product[];
  }) => {
    if (data.room_state !== undefined) setRoomState(data.room_state);
    if (data.products !== undefined) setProducts(data.products);
  };

  const handleStartOver = () => {
    setMessages([]);
    setSessionId(null);
    setRoomState(null);
    setProducts([]);
  };

  return (
    <div
      className="flex h-screen w-screen overflow-hidden"
      style={{ backgroundColor: "#faf8f5" }}
    >
      <ChatWindow
        messages={messages}
        setMessages={setMessages}
        sessionId={sessionId}
        setSessionId={setSessionId}
        isLoading={isLoading}
        setIsLoading={setIsLoading}
        input={input}
        setInput={setInput}
        onStartOver={handleStartOver}
        onApiResponse={handleApiResponse}
      />
      <RightPanel roomState={roomState} products={products} loading={isLoading} />
    </div>
  );
}

export default App;
