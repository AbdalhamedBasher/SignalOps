# SignalOps AI · Official Video & Live Demonstration Script

**Event**: MENA Ignite Hackathon (GSMA) · Prototype Phase  
**Theme**: Industrial & Enterprise AI Automation  
**Target Duration**: 3 minutes (180 seconds)  
**Target Environment**: Deployed Public Web Application (Production)

---

## Technical Setup & Pre-Flight Checklist

Before recording or presenting to evaluators:

1. **Verify Services**:
   - Backend API is online and responding at `/health`.
   - PostgreSQL migrations are up to date (`alembic upgrade head`).
   - Frontend is loaded at the deployed URL (e.g. `https://signalops-ai.vercel.app`).
   - Connection indicator in the header is green: **Connected · live updates active**.
2. **Reset / Prepare Seed State**:
   - Operator is initialized as **Nadia Karim** (`engineer`).
   - Keep a secondary browser window or terminal ready for `scripts/simulate.py`.
   - Keep fallback cached triage available in case remote free-tier model limits are encountered.

---

## 3-Minute Storyboard & Narration Track

```text
[ 0:00 - 0:30 ] Hook: The Problem — Alarm Fatigue & Blind Spots
       │
[ 0:30 - 1:00 ] Deterministic Ingestion & Sliding Window Correlation
       │
[ 1:00 - 1:45 ] CAMARA AI Agent Layer: Autonomously Invoking Network APIs
       │
[ 1:45 - 2:15 ] Inspecting the Reasoning Trace & Guardrail Citations
       │
[ 2:15 - 2:45 ] Role Governance & Supervisor Approval Gate
       │
[ 2:45 - 3:00 ] Architecture Summary & Close
```

---

### Segment 1: The Problem (0:00 – 0:30)

**Visual**:
- Camera opens on the clean SignalOps AI operations dashboard.
- Mouse hovers over the active metrics: Open Incidents, Critical Incidents, Affected Subscribers.

**English Voiceover**:
> *"In a modern telecommunications network, a single physical fiber cut doesn't trigger one clean notification. It unleashes a storm of dozens of cascading alarms across backhaul routers, radio base stations, and core registers within seconds. Network Operations Center (NOC) engineers drown in alarm noise, guessing at the root cause and flying blind on whether actual subscribers are cut off."*

**Arabic Voiceover Guide**:
> *"في شبكات الاتصالات الحديثة، انقطاع كابل ألياف بصرية واحد لا يرسل تنبيهاً واحداً فقط، بل يُطلق عاصفة من عشرات الإنذارات المتتالية عبر أجهزة التوجيه ومحطات البث والخوادم الأساسية خلال ثوانٍ. يواجه مهندسو مركز العمليات تشويشاً هائلاً دون معرفة السبب الجذري أو ما إذا كان المشتركون قد تأثروا فعلياً."*

---

### Segment 2: Deterministic Correlation (0:30 – 1:00)

**Action**:
- Run the alarm simulator from the terminal:
  ```bash
  python scripts/simulate.py --site RUH-315 --scenario backhaul --retry-last
  ```
- Point to the dashboard as alarms arrive over the WebSocket feed without a page refresh.

**Visual**:
- Live Event Feed scrolls the arriving alarms (`BACKHAUL_DOWN`, `CELL_OUT_OF_SERVICE`, `S1_LINK_FAILURE`, `VOLTE_REG_FAILURE`).
- The alarms collapse in real time into one critical incident (`INC-1001`).
- The duplicate final alarm is recognized and dropped idempotently without double-counting.

**English Voiceover**:
> *"SignalOps starts with rock-solid deterministic rules. Our sliding correlation window collapses this alarm burst into a single actionable incident. Notice that redelivered duplicate alarms are recognized and rejected idempotently. We derive incident severity from the worst symptom—never trusting raw claims blindly."*

**Arabic Voiceover Guide**:
> *"يبدأ SignalOps بقواعد محددة وصارمة. تقوم نافذة الربط الزمني الذكية بدمج هذه الإنذارات المتتالية في حادث واحد ذي أولوية حرجة، مع تجاهل الإنذارات المكررة تلقائياً دون تكرار الحساب."*

---

### Segment 3: The AI Agent Layer & CAMARA Orchestration (1:00 – 1:45)

**Action**:
- Click on **INC-1001** in the incident grid to open the Incident Details drawer.
- Click **"Retrieve Guidance"** in the Runbook panel.
- Click **"Run Triage"** in the CAMARA AI Triage panel. Show the loading state (*"Orchestrating agent…"*) as the agent runs.

**Visual**:
- The Triage Panel returns the structured verdict:
  - **Verdict**: `IMPACT CONFIRMED` (Red badge)
  - **Data Source**: `CAMARA Simulator / Nokia Network as Code`
  - **Network Evidence**: Plain-English facts about unreachable subscribers.

**English Voiceover**:
> *"Here is where most AI tools fail: they treat AI as a chatbot or hardcode subscriber numbers in a static lookup table. SignalOps does neither. Our AI Agent—built on Google Gemini and Pydantic AI—treats CAMARA network APIs as tools it autonomously decides to invoke.*
>
> *When we trigger triage, the agent formulates its hypotheses: Is this backhaul cut real? Are subscribers genuinely isolated? It autonomously calls CAMARA Device Reachability Status on Nokia Network as Code to verify registered devices at site RUH-104, queries Congestion Insights, reads the approved runbooks, and synthesizes a grounded verdict."*

**Arabic Voiceover Guide**:
> *"هنا يبرز الابتكار الحقيقي: نحن لا نستخدم الذكاء الاصطناعي كمحادثة سطحية ولا نعتمد على أرقام مشترين وهمية. وكيل الذكاء الاصطناعي لدينا، المبني باستخدام Google Gemini وPydantic AI، يتعامل مع واجهات شبكة CAMARA كأدوات يستدعيها ذاتياً للتأكد من وصول الأجهزة وحالة الازدحام قبل اتخاذ أي قرار."*

---

### Segment 4: The Reasoning Trace & Guardrail Audit (1:45 – 2:15)

**Action**:
- Highlight the **Agent Reasoning Trace** in the Triage Panel:
  - Step 1: `Called CAMARA Device Reachability Status for RUH-104`
  - Step 2: `Called CAMARA Congestion Insights for RUH-104`
  - Step 3: `Read 2 matched runbook section(s)`
- Scroll to the **Citations & Provenance** footer.

**Visual**:
- Show the step-by-step trace log with blue, amber, and green tags.
- Highlight the citations: `[RBS-0001] Transport and backhaul faults § Confirm the transport fault`.

**English Voiceover**:
> *"Judges reward seeing the agent think. The reasoning trace displays every network signal the agent inspected in sequence. And unlike unconstrained LLMs, our backend guardrail enforces zero hallucinations: if the model cites a runbook section it was not given, the report is rejected with HTTP 502. Nothing generated reaches an engineer uncited."*

**Arabic Voiceover Guide**:
> *"نمنح المشغلين شفافية كاملة لرؤية تسلسل تفكير الوكيل وخطوات استدعائه للواجهات. كما يضمن حاجز الأمان البرمجي لدينا رفض أي إرشادات غير موثقة من كتيبات العمل المعتمدة بنسبة 100%."*

---

### Segment 5: Role Governance & Supervisor Approval Gate (2:15 – 2:45)

**Action**:
- In the Runbook Guidance panel, locate the procedure: `Never reset equipment blind` (flagged with `Requires: supervisor`).
- Point to the disabled **Approve** button: `⚠️ Supervisor approval required (Nadia Karim is engineer)`.
- Click the Operator Switcher in the top navigation bar: switch to **Sam Okafor (Supervisor)**.
- Watch the **Approve** button instantly activate.
- Click **Approve**.
- Scroll to the bottom of the incident to show the updated audit event.

**Visual**:
- Smooth role transition in the UI without reloads.
- The approval records `Approved by sam.o` with a cryptographic timestamp.

**English Voiceover**:
> *"In enterprise telecommunications, AI must never make changes autonomously. Destructive procedures—like blind equipment resets—carry safety hazards. Notice that Nadia Karim, an engineer, cannot approve this high-risk step. The system enforces the supervisor gate declared in the runbook itself.*
>
> *When we switch to Supervisor Sam Okafor, the gate unlocks. Approval is attributed directly to his authenticated identity, creating an immutable audit trail."*

**Arabic Voiceover Guide**:
> *"في بيئات الاتصالات المؤسسية، لا يمكن ترك القرارات للذكاء الاصطناعي بشكل منفرد. العمليات الحساسة تتطلب موافقة المشرفين. النظام يمنع المهندس من تنفيذ العمليات الخطرة تلقائياً، ويسمح بها فقط عند اعتمادها من المشرف المعتمد، مع توثيقها في سجل تدقيق لا يمكن التلاعب به."*

---

### Segment 6: Conclusion (2:45 – 3:00)

**Visual**:
- Zoom out to the full dashboard showing the resolved incident state and live connection.
- Title card: **SignalOps AI · MENA Ignite Hackathon · GSMA**.

**English Voiceover**:
> *"SignalOps transforms telecom operations from reactive alarm firefighting into verified, CAMARA-backed incident orchestration. Deterministic correlation, autonomous agent tooling on Nokia Network as Code, and rigorous human-in-the-loop governance. Built for the future of autonomous networks. Thank you."*

**Arabic Voiceover Guide**:
> *"يحول SignalOps إدارة شبكات الاتصالات من التعامل العشوائي مع الإنذارات إلى منصة ذكية موثوقة تعتمد على واجهات CAMARA مع حوكمة بشرية صارمة. شكراً لكم."*

---

## Live Rehearsal Execution Commands

```powershell
# 1. Boot Backend (Terminal 1)
cd backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
uvicorn app.main:app --reload

# 2. Boot Frontend (Terminal 2)
cd frontend
npm run dev

# 3. Trigger Alarm Cascade (Terminal 3)
cd backend
.\.venv\Scripts\python.exe scripts\simulate.py --site RUH-104 --scenario backhaul

# 4. Optional CLI Triage Verification
.\.venv\Scripts\python.exe scripts\run_triage.py --incident INC-1001
```
