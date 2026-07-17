import { useEffect, useState } from "react";
import { MessageSquareText, Send, X } from "lucide-react";

import { effectiveFollowUpQuestion } from "./followUpText";
import type { ReviewResult } from "./types";


interface FollowUpPanelProps {
  item: ReviewResult | null;
  open: boolean;
  readOnly: boolean;
  onClose: () => void;
  onSubmit: (ruleId: string, question: string, answer: string) => Promise<void>;
}

export function FollowUpPanel({ item, open, readOnly, onClose, onSubmit }: FollowUpPanelProps) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setQuestion(item ? effectiveFollowUpQuestion(item) : "");
    setAnswer("");
  }, [item]);

  if (!open || !item) return null;

  const submit = async () => {
    if (!question.trim() || !answer.trim()) return;
    setSaving(true);
    try {
      await onSubmit(item.ruleId, question.trim(), answer.trim());
      setAnswer("");
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <aside className="follow-up-panel" aria-label="记录补问答案">
      <header>
        <MessageSquareText size={18} />
        <div><strong>补问记录</strong><span>{item.ruleId} · {item.ruleName}</span></div>
        <button className="icon-button" onClick={onClose} title="关闭"><X size={17} /></button>
      </header>
      <label>
        <span>实际补问</span>
        <textarea value={question} onChange={(event) => setQuestion(event.target.value)} readOnly={readOnly} />
      </label>
      <label>
        <span>被询问人回答</span>
        <textarea value={answer} onChange={(event) => setAnswer(event.target.value)} readOnly={readOnly} autoFocus />
      </label>
      {!readOnly && (
        <button className="primary-button compact" disabled={saving || !question.trim() || !answer.trim()} onClick={submit}>
          <Send size={15} />{saving ? "正在复核" : "保存并重审"}
        </button>
      )}
    </aside>
  );
}
