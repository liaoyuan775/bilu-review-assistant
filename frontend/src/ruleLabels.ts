const GROUP_LABELS: Record<string, string> = {
  META: "笔录与人员信息",
  PROC: "程序告知与确认",
  CASE: "报案与诈骗经过",
  PREV: "反诈宣传",
  RISK: "风险提示与处置",
  CASH: "取款与预约",
  TIME: "时间地点",
  PRIV: "个人信息泄露",
  LEAD: "首次引流",
  MOTIVE: "持续联系原因",
  CONTACT: "联系人与渠道切换",
  MONEY: "线上资金",
  OFFLINE: "线下交付",
  EXTRA: "补充事实",
  EVID: "证据留存",
};

const SCOPE_LABELS: Record<string, string> = {
  structural: "结构规则",
  common: "通用规则",
  conditional: "条件规则",
  repeated: "逐项核对",
  base: "基础规则",
};

const FACT_LABELS: Record<string, string> = {
  "record.started_at": "询问开始时间",
  "record.location": "询问地点",
  "record.interviewers": "询问人员",
  "record.respondent": "被询问人",
  "record.signatures": "签名确认",
  "procedure.truth_notice_confirmed": "如实作答告知确认",
  "procedure.rights_notice_read": "权利义务告知",
  "procedure.rights_request": "权利请求",
  "procedure.recusal_requested": "回避申请",
  "procedure.key_information_reconfirmed": "重要信息再次确认",
  "procedure.statement_confirmed_true": "陈述真实性确认",
  "procedure.record_reviewed": "笔录已阅看",
  "procedure.record_matches_statement": "笔录与陈述一致",
  "victim.name": "姓名",
  "victim.gender": "性别",
  "victim.age": "年龄",
  "victim.occupation": "职业",
  "victim.id_number": "身份证件号码",
  "victim.phone": "联系电话",
  "victim.education": "文化程度",
  "victim.employer": "工作单位",
  "case.report_reason": "报案原因",
  "case.fraud_method": "诈骗方式",
  "case.location": "案发地点",
  "case.initial_channel": "首次联系渠道",
  "case.contact_method": "联系方式",
  "case.total_loss": "损失总额",
  "case.timeline": "诈骗经过时间线",
  "case.initial_contact": "首次接触情况",
  "case.channel_changes": "联系渠道变化",
  "case.fraud_tools": "诈骗工具",
  "case.payment_reason": "付款原因",
  "case.payment_summary": "付款概况",
  "case.rebate_summary": "返利概况",
  "case.additional_statement": "其他补充事实",
  "prevention.received_publicity": "是否接受反诈宣传",
  "prevention.community_police_publicity": "社区民警反诈宣传",
  "prevention.anti_fraud_app_installed": "国家反诈中心 App 安装情况",
  "risk.payment_warning_received": "支付风险提示",
  "risk.payment_warning_channel": "风险提示渠道",
  "risk.payment_warning_content": "风险提示内容",
  "risk.account_loss_reported": "被骗后账户处置",
  "risk.loss_report_time": "账户处置时间",
  "risk.post_report_transfers": "报案后是否继续转账",
  "risk.phone_card_real_name": "电话卡实名情况",
  "risk.phone_warning_received": "电话卡风险提示",
  "risk.victim_chat_real_name": "被害人聊天账号实名",
  "risk.suspect_chat_real_name": "嫌疑人聊天账号实名",
  "evidence.voice_recording_exists": "语音通话是否录音",
  "evidence.voice_recording_available": "语音录音是否可提供",
  "evidence.records_retained": "相关记录是否留存",
  "evidence.record_types": "留存记录类型",
  "evidence.can_provide": "记录能否提供",
  "offline.suspect_appointment": "嫌疑人预约拿款信息",
  "offline.appointment_time": "预约时间",
  "offline.appointment_location": "预约地点",
  "offline.appointment_amount": "预约金额",
  "cash.bank_appointment": "银行取款预约",
  "cash.bank_warning_received": "银行风险提示",
  "cash.bank_warning_channel": "银行提示渠道",
  "cash.withdrawal_count": "取款笔数",
  "timeline.incident_at": "案发时间",
  "timeline.incident_district": "案发区县",
  "timeline.incident_street": "案发街道",
  "timeline.incident_community": "案发社区",
  "timeline.first_contact_at": "最早联系时间",
  "privacy.disclosure_occurred": "案发前是否泄露个人信息",
  "privacy.disclosure_time": "个人信息泄露时间",
  "privacy.disclosure_reason": "个人信息泄露原因",
  "privacy.disclosed_information": "泄露的个人信息",
  "contact.initial_channel": "首次联系渠道",
  "contact.initial_account": "首次联系账号",
  "contact.initial_content": "首次联系内容",
  "contact.switch_count": "后续渠道切换次数",
  "contact.chat_used": "是否使用聊天软件",
  "contact.phone_used": "是否通过电话联系",
  "contact.voice_call": "是否进行语音通话",
  "motive.continued_contact_reason": "持续联系原因",
  "money.gross_loss": "被骗总额",
  "money.rebate_total": "返利总额",
  "money.net_loss": "净损失",
  "money.transfer_control_method": "资金转出控制方式",
  "money.remote_control_used": "是否被远程控制",
  "money.credentials_disclosed": "是否泄露支付凭证",
  "online_money.transfer_count": "线上转账笔数",
  "online_money.total": "线上转账总额",
  "online_money.used": "是否发生线上资金转移",
  "offline.handoff_count": "线下交付次数",
  "offline.property_source": "现金或实物来源",
  "offline.used": "是否发生取现或线下交付",
  "special.ecommerce_logistics_impersonation": "是否涉及电商物流冒充场景",
  "special.gambling_related": "是否涉及赌博场景",
};

const ENTITY_LABELS: Record<string, { label: string; counter: string }> = {
  cs: { label: "后续联系人", counter: "个" },
  contact_switch: { label: "后续联系人", counter: "个" },
  transfer: { label: "转账", counter: "笔" },
  rebate: { label: "返利", counter: "笔" },
  withdrawal: { label: "取款", counter: "笔" },
  offline_handoff: { label: "线下交付", counter: "次" },
};

const ENTITY_COLLECTION_LABELS: Record<string, string> = {
  contact_switches: "后续联系人切换",
  transfers: "转账记录",
  rebates: "返利记录",
  withdrawals: "取款记录",
  offline_handoffs: "线下交付记录",
};

const DOMAIN_LABELS: Record<string, string> = {
  header_procedure: "笔录头、个人信息与程序确认",
  case_timeline: "案件经过、时间地点与主观原因",
  contact_channels: "首次接触与联系渠道切换",
  risk_and_evidence: "反诈宣传、风险提示与证据留存",
  online_money: "线上资金流",
  offline_delivery: "取现与线下交付",
  special_scenarios: "特殊场景与补充事实",
};

const ENTITY_FIELD_LABELS: Record<string, string> = {
  time: "时间",
  channel: "联系渠道",
  account: "账号",
  important_information: "重要信息",
  details: "详细内容",
  amount: "金额",
  payment_method: "支付方式",
  payer_account: "付款账号",
  recipient_account: "收款账号",
  transaction_id: "交易流水号",
  method: "方式",
  bank: "银行",
  branch: "银行网点",
  address: "地址",
  location: "地点",
  property_type: "财物类型",
  amount_or_value: "金额或价值",
  recipient_or_logistics: "接收人或物流信息",
};

const displayEntityField = (fact: string) => {
  const countMatch = fact.match(/^([a-z_]+)\.count$/);
  if (countMatch) {
    const collection = ENTITY_COLLECTION_LABELS[countMatch[1]];
    return collection ? `${collection}数量` : null;
  }
  const entityMatch = fact.match(/^([a-z_]+)_(\d+)\.([a-z_]+)$/);
  if (!entityMatch) return null;
  const entity = ENTITY_LABELS[entityMatch[1]];
  const field = ENTITY_FIELD_LABELS[entityMatch[3]];
  if (!entity || !field) return null;
  return `第${Number(entityMatch[2])}${entity.counter}${entity.label}${field}`;
};

export const displayGroupLabel = (group: string) => GROUP_LABELS[group] ?? group;
export const displayRuleScope = (scope: string) => SCOPE_LABELS[scope] ?? scope;
export const displayDomainLabel = (domain: string) => DOMAIN_LABELS[domain] ?? domain;
export const displayEntityTypeLabel = (entity: string) => ENTITY_COLLECTION_LABELS[entity] ?? entity;
export const displayFactLabel = (fact: string) => FACT_LABELS[fact] ?? displayEntityField(fact) ?? fact;

export const displayReviewReason = (reason: string) => reason.replace(
  /\b[a-z][a-z0-9_]*(?:_[0-9]+)?\.[a-z][a-z0-9_]*\b/g,
  (field) => displayFactLabel(field),
);
