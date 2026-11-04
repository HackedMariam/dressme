import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import type { ChatTurn, ShownItem, TraceStep } from "./api";
import { asset } from "../../lib/api";
import PlannerPanel from "./PlannerPanel";

export type DrawerTab = "plan" | "chat";

export type Message = ChatTurn & { trace?: TraceStep[]; items?: ShownItem[] };

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) =>
    part.startsWith("**") ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : part.startsWith("`") ? (
      <code key={i} className="text-[12px] bg-[#F0EFEA] px-1 rounded">{part.slice(1, -1)}</code>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

function AgentMarkdown({ text }: { text: string }) {
  return (
    <div className="space-y-1.5">
      {text.split("\n").map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed) return null;
        const bullet = trimmed.match(/^[-*]\s+(.*)/);
        return bullet ? <p key={i} className="pl-4">• {inline(bullet[1])}</p> : <p key={i}>{inline(trimmed)}</p>;
      })}
    </div>
  );
}

function TraceView({ trace }: { trace: TraceStep[] }) {
  const [open, setOpen] = useState(false);
  if (trace.length === 0) return null;
  return (
    <div className="mt-2">
      <button onClick={() => setOpen(!open)} className="text-[11px] text-[#556B2F] font-semibold hover:underline">
        {open ? "Hide" : "Show"} agent pipeline · {trace.length} tool call{trace.length > 1 ? "s" : ""}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {trace.map((entry, i) => (
            <div key={i} className="bg-[#1C1C1C] rounded-lg p-3 text-[11px]">
              <p className="text-white/80 font-mono">
                <span className="text-[#8FA866]">step {entry.step}</span> · {entry.tool}({JSON.stringify(entry.arguments)})
              </p>
              <pre className="text-white/50 mt-1.5 max-h-40 overflow-auto whitespace-pre-wrap">{JSON.stringify(entry.result, null, 2)}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Owned pieces the agent talked about, as photo cards.
function ShownItems({ items }: { items: ShownItem[] }) {
  return (
    <div className="mt-3 grid grid-cols-2 gap-2">
      {items.map((item) => (
        <div key={item.id} className="flex items-center gap-2 rounded-lg border border-[#E2E0D8] bg-[#FAF9F6] p-1.5">
          <div className="grid h-16 w-12 shrink-0 place-items-center overflow-hidden rounded bg-[#F0EFEA] text-[9px] text-[#8C8A82]">
            {item.image_url ? (
              <img src={asset(item.image_url)} alt={item.name} loading="lazy" className="h-full w-full object-contain" />
            ) : (
              "No photo"
            )}
          </div>
          <div className="min-w-0">
            <p className="truncate text-[11px] font-semibold text-[#1C1C1C]" title={item.name}>{item.name}</p>
            <p className="truncate text-[10px] capitalize text-[#8C8A82]">
              {[item.colors?.[0], (item.subcategory ?? item.category).replace(/_/g, " ")].filter(Boolean).join(" · ")}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AgentDrawer({
  open,
  onClose,
  messages,
  thinking,
  error,
  onSend,
  suggestion,
  tab,
  onTab,
}: {
  open: boolean;
  onClose: () => void;
  messages: Message[];
  thinking: boolean;
  error: string | null;
  onSend: (text: string) => void;
  suggestion: string;
  tab: DrawerTab;
  onTab: (tab: DrawerTab) => void;
}) {
  const [input, setInput] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages, thinking]);
  const send = (text: string) => {
    onSend(text);
    setInput("");
  };
  return (
    // Hidden, not unmounted, when closed: a plan on screen survives closing the drawer.
    <div className={`fixed top-0 right-0 bottom-0 w-[520px] max-w-full bg-white border-l border-[#E2E0D8] shadow-[-20px_0_40px_rgba(40,30,20,.12)] z-[60] flex flex-col ${open ? "" : "hidden"}`}>
      <div className="px-5 pt-4 border-b border-[#E2E0D8]">
        <div className="flex items-start gap-3">
          <div className="flex-1">
            <p className="text-[11px] font-bold tracking-[1.8px] uppercase text-[#556B2F]">BO3 · Wardrobe agent</p>
            <p className="text-[11px] text-[#8C8A82] mt-0.5">
              Rules decide the gaps · learned ranker · FashionCLIP · language model plans and explains
            </p>
          </div>
          <button onClick={onClose} aria-label="Close agent" className="text-[#8C8A82] hover:text-[#1C1C1C] text-lg">×</button>
        </div>
        <div role="tablist" aria-label="Agent mode" className="mt-3 flex gap-1">
          {([["plan", "✦ Shopping planner"], ["chat", "Chat"]] as const).map(([id, label]) => (
            <button
              key={id}
              role="tab"
              aria-selected={tab === id}
              onClick={() => onTab(id)}
              className={`rounded-t-lg border-b-2 px-3.5 py-2 text-[12.5px] font-semibold transition-colors ${
                tab === id ? "border-[#556B2F] text-[#1C1C1C]" : "border-transparent text-[#8C8A82] hover:text-[#1C1C1C]"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className={tab === "plan" ? "contents" : "hidden"}>
        <PlannerPanel />
      </div>

      {tab === "chat" && (
      <>
      <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-[#FAF9F6]">
        {messages.length === 0 && (
          <button
            onClick={() => send(suggestion)}
            className="block w-full text-left text-xs bg-white border border-[#E2E0D8] px-3 py-2 rounded-lg hover:border-[#556B2F]"
          >
            {suggestion}
          </button>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
            <div
              className={`rounded-2xl px-4 py-3 text-[13px] leading-relaxed ${
                m.role === "user" ? "bg-[#1C1C1C] text-white rounded-tr-none max-w-[85%]" : "bg-white border border-[#E2E0D8] text-[#1C1C1C] rounded-tl-none"
              }`}
            >
              {m.role === "assistant" ? <AgentMarkdown text={m.content} /> : m.content}
              {m.items && m.items.length > 0 && <ShownItems items={m.items} />}
              {m.trace && <TraceView trace={m.trace} />}
            </div>
          </div>
        ))}
        {thinking && <p className="text-xs text-[#8C8A82]">Agent is calling tools…</p>}
        {error && <p className="text-xs text-[#9A5A3C]">Error: {error}</p>}
        <div ref={end} />
      </div>

      <div className="p-3 border-t border-[#E2E0D8] flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
          placeholder="Ask about your wardrobe gaps…"
          className="flex-1 px-3 py-2.5 bg-white border border-[#E2E0D8] rounded-xl text-sm outline-none focus:border-[#556B2F]"
        />
        <button
          onClick={() => send(input)}
          disabled={thinking}
          className="bg-[#556B2F] hover:bg-[#6B8A3A] disabled:opacity-50 text-white px-4 rounded-xl text-sm font-semibold"
        >
          Send
        </button>
      </div>
      </>
      )}
    </div>
  );
}
