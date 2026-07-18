import { useEffect, useRef, useState } from "react";
import { ChevronDown, LockKeyhole } from "lucide-react";

import type { VictimProfile } from "./types";
import { getVictimAvatarVariant, getVictimInitial } from "./victimProfile";

export const profileFields: Array<{
  key: keyof VictimProfile;
  label: string;
  format?: (value: VictimProfile[keyof VictimProfile]) => string;
}> = [
  { key: "name", label: "姓名" },
  { key: "gender", label: "性别" },
  { key: "age", label: "年龄", format: (value) => `${value}岁` },
  { key: "ethnicity", label: "民族" },
  { key: "idNumber", label: "身份证号" },
  { key: "contact", label: "联系方式" },
  { key: "employer", label: "工作单位" },
  { key: "address", label: "住址" },
];

export function VictimProfileCard({ profile }: { profile: VictimProfile }) {
  const [pinned, setPinned] = useState(false);
  const [hoverOpen, setHoverOpen] = useState(false);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const name = profile.name ?? "姓名未提取";
  const summary = [profile.gender, profile.age === null ? null : `${profile.age}岁`, profile.ethnicity].filter(Boolean).join(" · ");

  useEffect(() => {
    if (!pinned) return;
    const closeWhenClickingOutside = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setPinned(false);
    };
    document.addEventListener("pointerdown", closeWhenClickingOutside);
    return () => document.removeEventListener("pointerdown", closeWhenClickingOutside);
  }, [pinned]);

  return (
    <div
      ref={containerRef}
      className={`victim-profile ${pinned ? "is-pinned" : ""} ${hoverOpen ? "is-hover-open" : ""} ${keyboardOpen ? "is-keyboard-open" : ""}`}
      onPointerEnter={() => setHoverOpen(true)}
      onPointerLeave={() => setHoverOpen(false)}
      onFocusCapture={() => setKeyboardOpen(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setKeyboardOpen(false);
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setPinned(false);
          setHoverOpen(false);
          setKeyboardOpen(false);
        }
      }}
    >
      <button
        className="victim-profile-trigger"
        type="button"
        aria-expanded={pinned}
        aria-haspopup="dialog"
        aria-controls="victim-profile-detail"
        onClick={() => {
          setKeyboardOpen(false);
          setPinned((current) => !current);
        }}
      >
        <span className={`victim-avatar ${getVictimAvatarVariant(name)}`} aria-hidden="true">{getVictimInitial(name)}</span>
        <span className="victim-profile-summary">
          <small>被害人</small>
          <strong>{name}</strong>
          <span>{summary || "基础信息待补充"}</span>
        </span>
        <ChevronDown size={16} aria-hidden="true" />
      </button>

      <div className="victim-profile-popover" id="victim-profile-detail" role="dialog" aria-label="被害人详细信息">
        <div className="victim-profile-popover-heading">
          <span className={`victim-avatar ${getVictimAvatarVariant(name)}`} aria-hidden="true">{getVictimInitial(name)}</span>
          <span><small>被害人信息</small><strong>{name}</strong></span>
        </div>
        <dl>
          {profileFields.map(({ key, label, format }) => {
            const value = profile[key];
            return (
              <div className={key === "employer" || key === "address" ? "profile-field wide" : "profile-field"} key={key}>
                <dt>{label}</dt>
                <dd>{value === null ? "未提取" : format ? format(value) : value}</dd>
              </div>
            );
          })}
        </dl>
        <p><LockKeyhole size={13} />个人信息按笔录原文展示</p>
      </div>
    </div>
  );
}
