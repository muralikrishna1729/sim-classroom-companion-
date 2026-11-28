import { useEffect, useMemo, useState } from "react";
import {
  Activity, ArrowDownRight, ArrowRight, Bell, BookOpen, Building2, CalendarDays, Check,
  CheckCircle2, ChevronDown, CircleHelp, ClipboardList, Clock3, GraduationCap,
  LayoutDashboard, LogOut, Menu, Plus, Search, Send, Settings, ShieldCheck,
  Sparkles, Users, X,
} from "lucide-react";
import { assignmentApi, authApi, classroomApi, notificationApi, schoolApi, type Assignment, type Classroom, type Notification, type School, type User } from "./api";

type Role = "teacher" | "student";
type Notice = { kind: "success" | "error"; text: string };

function getApiErrorMessage(error: any, fallback: string): string {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item: any) => {
      const location = Array.isArray(item?.loc) ? item.loc.filter((part: unknown) => part !== "body").join(" → ") : "";
      const message = typeof item?.msg === "string" ? item.msg : "Invalid value";
      return location ? location + ": " + message : message;
    }).join("; ");
  }
  return fallback;
}

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [role, setRole] = useState<Role>("teacher");
  const [page, setPage] = useState("Overview");
  const [classrooms, setClassrooms] = useState<Classroom[]>([]);
  const [schools, setSchools] = useState<School[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [loading, setLoading] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [search, setSearch] = useState("");

  const refresh = async () => {
    setLoading(true);
    try {
      const [roomData, assignmentData, notificationData, schoolData] = await Promise.all([
        classroomApi.list(), assignmentApi.list(), notificationApi.list(), schoolApi.list(),
      ]);
      setClassrooms(roomData);
      setSchools(schoolData);
      setAssignments(assignmentData);
      setNotifications(notificationData.items || []);
    } catch (error: any) {
      if (error?.response?.status === 401) {
        authApi.logout(); setUser(null);
      } else setNotice({ kind: "error", text: getApiErrorMessage(error, "Couldn't load your classroom data.") });
    } finally { setLoading(false); }
  };

  useEffect(() => {
    if (!localStorage.getItem("sim_access_token")) return;
    authApi.me().then(setUser).catch(() => { authApi.logout(); setUser(null); });
  }, []);
  useEffect(() => { if (user) void refresh(); }, [user]);

  const visibleAssignments = useMemo(() => assignments.filter((item) =>
    item.title.toLowerCase().includes(search.toLowerCase())), [assignments, search]);

  const authenticate = async (event: React.FormEvent) => {
    event.preventDefault(); setLoading(true); setNotice(null);
    try {
      if (authMode === "login") await authApi.login(email, password);
      else await authApi.register(fullName, email, password);
      setUser(await authApi.me());
      setNotice({ kind: "success", text: "Welcome to Classroom Companion." });
    } catch (error: any) {
      setNotice({ kind: "error", text: getApiErrorMessage(error, "Authentication failed. Check your details and try again.") });
    } finally { setLoading(false); }
  };

  const signOut = () => { authApi.logout(); setUser(null); setClassrooms([]); setAssignments([]); };
  const navItems = role === "teacher"
    ? [{ label: "Overview", icon: LayoutDashboard }, { label: "Classrooms", icon: Users }, { label: "Assignments", icon: ClipboardList }, { label: "Submissions", icon: BookOpen }, { label: "School setup", icon: Building2 }]
    : [{ label: "Overview", icon: LayoutDashboard }, { label: "My assignments", icon: ClipboardList }, { label: "Feedback", icon: BookOpen }];

  if (!user) return <AuthScreen mode={authMode} setMode={setAuthMode} email={email} setEmail={setEmail} password={password} setPassword={setPassword} fullName={fullName} setFullName={setFullName} submit={authenticate} loading={loading} notice={notice} />;

  const pending = assignments.filter(a => !["completed", "submitted"].includes((a.my_status || "").toLowerCase()));
  const completed = assignments.filter(a => ["completed", "submitted"].includes((a.my_status || "").toLowerCase()));

  return <div className="app-shell">
    <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}>
      <div className="brand"><div className="brand-mark"><GraduationCap size={22}/></div><div><strong>classroom<span>.</span></strong><small>COMPANION</small></div><button className="icon-button mobile-close" onClick={() => setMobileNav(false)}><X size={18}/></button></div>
      <div className="workspace-label">WORKSPACE</div>
      <div className="role-switch"><button className={role === "teacher" ? "active" : ""} onClick={() => {setRole("teacher");setPage("Overview");}}>Teacher</button><button className={role === "student" ? "active" : ""} onClick={() => {setRole("student");setPage("Overview");}}>Student</button></div>
      <div className="nav-caption">MENU</div>
      <nav>{navItems.map(item => <button key={item.label} className={`nav-item ${page === item.label ? "selected" : ""}`} onClick={() => {setPage(item.label);setMobileNav(false);}}><item.icon size={18}/><span>{item.label}</span>{item.label === "Submissions" && <span className="nav-count">{assignments.length}</span>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="help-card"><div className="help-icon"><CircleHelp size={18}/></div><strong>Need a hand?</strong><p>Find your way around the classroom.</p><button onClick={() => setNotice({kind:"success",text:"Help center is coming soon."})}>Visit help center <ArrowRight size={13}/></button></div><button className="nav-item"><Settings size={18}/><span>Settings</span></button><div className="profile-row"><div className="avatar">{user.full_name.slice(0,1).toUpperCase()}</div><div className="profile-meta"><strong>{user.full_name}</strong><small>{user.email}</small></div><button className="icon-button" title="Sign out" onClick={signOut}><LogOut size={17}/></button></div></div>
    </aside>
    {mobileNav && <button className="scrim" onClick={() => setMobileNav(false)} aria-label="Close menu"/>}
    <main className="main-area">
      <header className="topbar"><button className="icon-button menu-toggle" onClick={() => setMobileNav(true)}><Menu size={20}/></button><div className="breadcrumb">Workspace <span>/</span> <strong>{page}</strong></div><div className="top-actions"><div className="search-box"><Search size={16}/><input placeholder="Search anything..." value={search} onChange={e=>setSearch(e.target.value)}/><kbd>⌘ K</kbd></div><button className="icon-button notification-button" onClick={() => setPage("Notifications")}><Bell size={19}/>{notifications.some(n=>!n.read_at) && <i/>}</button><div className="top-avatar">{user.full_name.slice(0,1).toUpperCase()}</div></div></header>
      <div className="page-content">
        {notice && <div className={`notice ${notice.kind}`}>{notice.kind === "success" ? <CheckCircle2 size={17}/> : <CircleHelp size={17}/>}<span>{notice.text}</span><button onClick={()=>setNotice(null)}><X size={15}/></button></div>}
        {page === "Overview" && <><div className="welcome-row"><div><div className="eyebrow"><Sparkles size={14}/> YOUR CLASSROOM, IN SYNC</div><h1>{role === "teacher" ? "Good to see you" : "Ready to learn"}, {user.full_name.split(" ")[0]} <span>✦</span></h1><p>{role === "teacher" ? "Here's what's happening across your classrooms today." : "Pick up where you left off and keep making progress."}</p></div><div className="date-chip"><CalendarDays size={16}/>{new Date().toLocaleDateString("en-IN",{weekday:"short",day:"numeric",month:"short",year:"numeric"})}</div></div>
          <section className="hero-card"><div className="hero-copy"><div className="hero-pill"><span/> CLASSROOM OVERVIEW</div><h2>{role === "teacher" ? "A clearer view of every learner." : "Small steps make big progress."}</h2><p>{role === "teacher" ? "Bring assignments, student progress and feedback together in one calm workspace." : "Your assignments and feedback, all in one place. Let's make today count."}</p><button className="hero-button" onClick={()=>setPage(role === "teacher" ? "Assignments" : "My assignments")}>{role === "teacher" ? "Manage assignments" : "View my assignments"} <ArrowRight size={16}/></button></div><div className="hero-art"><div className="art-orbit orbit-one"/><div className="art-orbit orbit-two"/><div className="art-note note-one"><CheckCircle2 size={16}/> On track</div><div className="art-note note-two"><BookOpen size={16}/> Keep learning</div><div className="art-board"><div className="board-top"><span/><span/><span/></div><div className="board-lines"><i/><i/><i/></div><div className="board-chart"><b/><b/><b/><b/><b/><b/><b/></div></div><div className="art-spark">✦</div></div></section>
          <div className="section-heading"><div><h3>Your snapshot</h3><p>A quick look at the numbers that matter.</p></div><button className="text-button" onClick={()=>void refresh()}>Refresh data <ArrowRight size={14}/></button></div>
          <div className="stats-grid">{(role === "teacher" ? [{label:"Classrooms",value:classrooms.length,meta:"Your learning spaces",icon:Users,tone:"violet"},{label:"Assignments",value:assignments.length,meta:"Across all classrooms",icon:ClipboardList,tone:"blue"},{label:"In progress",value:pending.length,meta:"Need a little attention",icon:Activity,tone:"amber"},{label:"Completed",value:completed.length,meta:"Work submitted or done",icon:CheckCircle2,tone:"green"}] : [{label:"My assignments",value:assignments.length,meta:"Assigned to you",icon:ClipboardList,tone:"violet"},{label:"To do",value:pending.length,meta:"Ready when you are",icon:Clock3,tone:"amber"},{label:"Submitted",value:completed.length,meta:"Great work so far",icon:CheckCircle2,tone:"green"},{label:"Notifications",value:notifications.length,meta:"Classroom updates",icon:Bell,tone:"blue"}]).map(stat=><div className="stat-card" key={stat.label}><div className="stat-top"><span>{stat.label}</span><div className={`stat-icon ${stat.tone}`}><stat.icon size={18}/></div></div><strong>{stat.value}</strong><small>{stat.meta}</small></div>)}</div>
          <div className="content-grid"><section className="panel assignments-panel"><div className="panel-heading"><div><h3>{role === "teacher" ? "Recent assignments" : "Up next"}</h3><p>{role === "teacher" ? "Keep an eye on the work in your classrooms." : "Your latest classroom work."}</p></div><button className="text-button" onClick={()=>setPage(role === "teacher" ? "Assignments" : "My assignments")}>View all <ArrowRight size={14}/></button></div>{loading ? <div className="empty-state">Loading your classroom…</div> : visibleAssignments.length ? visibleAssignments.slice(0,4).map(a=><AssignmentRow key={a.id} item={a}/>) : <div className="empty-state"><div className="empty-icon"><ClipboardList size={21}/></div><strong>No assignments yet</strong><span>{role === "teacher" ? "Create your first assignment to get started." : "Your teacher's assignments will appear here."}</span>{role === "teacher" && <button className="primary-button small" onClick={()=>setShowCreate(true)}><Plus size={15}/> Create assignment</button>}</div>}</section>
            <section className="panel activity-panel"><div className="panel-heading"><div><h3>Recent activity</h3><p>Updates from your classroom.</p></div><span className="live-dot">LIVE</span></div>{notifications.slice(0,4).length ? notifications.slice(0,4).map(n=><div className="activity-row" key={n.id}><div className="activity-icon"><Bell size={15}/></div><div><strong>{n.title}</strong><p>{n.message}</p><small>{new Date(n.created_at).toLocaleString()}</small></div></div>) : <div className="empty-state compact">You're all caught up.<span>New classroom updates will show here.</span></div>}</section></div>
        </>}
        {(page === "Assignments" || page === "My assignments") && <><div className="page-title-row"><div><div className="eyebrow">STAY ON TRACK</div><h1>{page}</h1><p>{role === "teacher" ? "Create, organize and follow assignment progress." : "Everything you need to finish your classroom work."}</p></div>{role === "teacher" && <button className="primary-button" onClick={()=>setShowCreate(true)}><Plus size={17}/> New assignment</button>}</div><section className="panel table-panel"><div className="panel-heading"><div><h3>All assignments</h3><p>{visibleAssignments.length} assignments found</p></div><span className="filter-chip">All statuses <ChevronDown size={14}/></span></div>{visibleAssignments.length ? visibleAssignments.map(a=><AssignmentRow key={a.id} item={a}/>) : <div className="empty-state">No assignments found.</div>}</section></>}
        {page === "Classrooms" && <><div className="page-title-row"><div><div className="eyebrow">YOUR LEARNING SPACES</div><h1>Classrooms</h1><p>All the classrooms connected to your account.</p></div></div><div className="classroom-grid">{classrooms.map((c,i)=><div className="classroom-card" key={c.id}><div className={`classroom-cover cover-${i%4}`}><GraduationCap size={28}/><span>0{i+1}</span></div><div className="classroom-body"><small>{c.grade_label || "CLASSROOM"}</small><h3>{c.name}</h3><p>Classroom workspace</p></div></div>)}{!classrooms.length && <div className="panel empty-state">No classrooms are linked to your account yet.</div>}</div></>}
        {page === "School setup" && <SchoolSetup user={user} schools={schools} classrooms={classrooms} refresh={refresh} notify={setNotice}/>}
        {page === "Submissions" && <section className="panel"><div className="panel-heading"><div><h3>Submission review</h3><p>Teacher review workspace</p></div></div><div className="empty-state">Your submission review endpoint is ready. We'll connect the detailed review table in the next frontend iteration.</div></section>}
        {page === "Feedback" && <section className="panel"><div className="empty-state">Feedback from your teacher will appear here after a submission is reviewed.</div></section>}
        {page === "Notifications" && <section className="panel"><div className="panel-heading"><div><h3>Notifications</h3><p>Stay up to date with classroom activity.</p></div></div>{notifications.map(n=><div className="activity-row" key={n.id}><div className="activity-icon"><Bell size={15}/></div><div><strong>{n.title}</strong><p>{n.message}</p><small>{new Date(n.created_at).toLocaleString()}</small></div></div>)}{!notifications.length && <div className="empty-state">No notifications yet.</div>}</section>}
      </div>
      <footer className="footer"><span>© 2026 SIM Classroom Companion</span><span>Made for better learning <span className="footer-heart">✦</span></span></footer>
    </main>
    {showCreate && <CreateAssignment classrooms={classrooms} schools={schools} close={()=>setShowCreate(false)} created={()=>{setShowCreate(false);setNotice({kind:"success",text:"Assignment created and distributed."});void refresh();}} error={text=>setNotice({kind:"error",text})}/>}
  </div>;
}


function SchoolSetup({user,schools,classrooms,refresh,notify}:{user:User;schools:School[];classrooms:Classroom[];refresh:()=>Promise<void>;notify:(notice:Notice)=>void}) {
  const [schoolName,setSchoolName]=useState("");
  const [className,setClassName]=useState("");
  const [grade,setGrade]=useState("");
  const [selectedSchool,setSelectedSchool]=useState(schools[0]?.id||"");
  const [selectedClass,setSelectedClass]=useState(classrooms[0]?.id||"");
  const [studentId,setStudentId]=useState("");
  const [busy,setBusy]=useState(false);
  useEffect(()=>{if(!selectedSchool&&schools[0])setSelectedSchool(schools[0].id);},[schools,selectedSchool]);
  useEffect(()=>{if(!selectedClass&&classrooms[0])setSelectedClass(classrooms[0].id);},[classrooms,selectedClass]);
  const run=async(action:()=>Promise<unknown>,success:string)=>{
    setBusy(true);
    try{await action();await refresh();notify({kind:"success",text:success});}
    catch(error:any){notify({kind:"error",text:getApiErrorMessage(error,"The setup action could not be completed.")});}
    finally{setBusy(false);}
  };
  return <div className="setup-stack">
    <div className="page-title-row"><div><div className="eyebrow">GET YOUR WORKSPACE READY</div><h1>School setup</h1><p>Create a school, organize classrooms and connect people using their registered accounts.</p></div></div>
    <section className="panel setup-panel"><div className="panel-heading"><div><h3>1. Create your school</h3><p>The account that creates the school becomes its coordinator.</p></div><span className="status-pill green">{schools.length} schools</span></div>
      <form onSubmit={e=>{e.preventDefault();void run(async()=>{const school=await schoolApi.create({name:schoolName,timezone:"Asia/Kolkata"});setSelectedSchool(school.id);setSchoolName("");},"School created. You are now its coordinator.");}}>
        <label>School name<input required minLength={2} value={schoolName} onChange={e=>setSchoolName(e.target.value)} placeholder="e.g. Sunrise Public School"/></label>
        <label>Timezone<input value="Asia/Kolkata" readOnly/></label>
        <button className="primary-button" disabled={busy}><Plus size={15}/> Create school</button>
      </form>
      {schools.length>0&&<p className="setup-hint">Your schools: {schools.map(s=>s.name).join(", ")}</p>}
    </section>
    <section className="panel setup-panel"><div className="panel-heading"><div><h3>2. Create a classroom</h3><p>Choose a school you coordinate.</p></div></div>
      <form onSubmit={e=>{e.preventDefault();void run(async()=>{await classroomApi.create({school_id:selectedSchool,name:className,grade_label:grade||null});setClassName("");setGrade("");},"Classroom created successfully.");}}>
        <label>School<select required value={selectedSchool} onChange={e=>setSelectedSchool(e.target.value)}><option value="">Select a school</option>{schools.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
        <label>Classroom name<input required minLength={2} value={className} onChange={e=>setClassName(e.target.value)} placeholder="e.g. Class 10-A"/></label>
        <label>Grade (optional)<input value={grade} onChange={e=>setGrade(e.target.value)} placeholder="e.g. Grade 10"/></label>
        <button className="primary-button" disabled={busy||!schools.length}><Plus size={15}/> Create classroom</button>
      </form>
      {classrooms.length>0&&<p className="setup-hint">Available classrooms: {classrooms.map(c=>c.name).join(", ")}</p>}
    </section>
    <section className="panel setup-panel"><div className="panel-heading"><div><h3>3. Activate your teacher access</h3><p>As school coordinator, you can add your own account as a teacher.</p></div></div>
      <label>Classroom<select value={selectedClass} onChange={e=>setSelectedClass(e.target.value)}><option value="">Select a classroom</option>{classrooms.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <button className="primary-button" disabled={busy||!selectedClass} onClick={()=>void run(()=>classroomApi.addTeacher(selectedClass,user.id),"Your teacher membership is active. You can now create assignments.")}><Check size={15}/> Activate my teacher access</button>
    </section>
    <section className="panel setup-panel"><div className="panel-heading"><div><h3>4. Add a student</h3><p>Students must register first. Use their account ID from the user record for now.</p></div></div>
      <label>Classroom<select value={selectedClass} onChange={e=>setSelectedClass(e.target.value)}><option value="">Select a classroom</option>{classrooms.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <label>Student user ID<input value={studentId} onChange={e=>setStudentId(e.target.value)} placeholder="Paste the student's UUID"/></label>
      <button className="primary-button" disabled={busy||!selectedClass||!studentId.trim()} onClick={()=>void run(()=>classroomApi.addStudent(selectedClass,studentId.trim()),"Student added to the classroom.")}><Users size={15}/> Add student</button>
    </section>
  </div>;
}

function AssignmentRow({item}:{item:Assignment}) {
  const status = (item.my_status || item.status || "assigned").replace(/_/g, " ");
  const tone = ["completed","submitted"].includes(status.toLowerCase()) ? "green" : status.toLowerCase()==="blocked" ? "red" : "amber";
  return <div className="assignment-row"><div className="assignment-symbol"><BookOpen size={18}/></div><div className="assignment-info"><strong>{item.title}</strong><small>{item.instructions}</small></div><span className={`status-pill ${tone}`}>{status}</span><div className="due-date"><CalendarDays size={14}/>{item.due_at ? new Date(item.due_at).toLocaleDateString() : "No due date"}</div></div>;
}

function CreateAssignment({classrooms,schools,close,created,error}:{classrooms:Classroom[];schools:School[];close:()=>void;created:()=>void;error:(text:string)=>void}) {
  const [classroom,setClassroom]=useState(classrooms[0]?.id||"");
  const [title,setTitle]=useState(""); const [instructions,setInstructions]=useState("");
  const [due,setDue]=useState(""); const [saving,setSaving]=useState(false);
  const submit=async(e:React.FormEvent)=>{e.preventDefault();if(!classroom){error("Create or join a classroom before assigning work.");return;}const selectedClassroom=classrooms.find(item=>item.id===classroom);const school=schools.find(item=>item.id===selectedClassroom?.school_id);if(!school){error("We couldn't determine this classroom's school timezone. Refresh your data and try again.");return;}setSaving(true);try{await assignmentApi.create({classroom_id:classroom,title,instructions,target_type:"class",timezone:school.timezone,due_at:due?new Date(due).toISOString():null});created();}catch(err:any){error(getApiErrorMessage(err, "Couldn't create the assignment."));}finally{setSaving(false);}};
  return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)close();}}><form className="modal" onSubmit={submit}><div className="modal-head"><div><div className="eyebrow">NEW CLASSROOM TASK</div><h2>Create assignment</h2><p>Share clear instructions and a deadline.</p></div><button type="button" className="icon-button" onClick={close}><X size={19}/></button></div><label>Classroom<select required value={classroom} onChange={e=>setClassroom(e.target.value)}><option value="">Select classroom</option>{classrooms.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>Assignment title<input required minLength={2} value={title} onChange={e=>setTitle(e.target.value)} placeholder="e.g. Science project: our solar system"/></label><label>Instructions<textarea required rows={4} value={instructions} onChange={e=>setInstructions(e.target.value)} placeholder="Explain what students need to complete…"/></label><label>Due date and time<input type="datetime-local" value={due} onChange={e=>setDue(e.target.value)}/></label><div className="modal-actions"><button type="button" className="secondary-button" onClick={close}>Cancel</button><button className="primary-button" disabled={saving}>{saving?"Creating…":<><Send size={15}/> Create assignment</>}</button></div></form></div>;
}

function AuthScreen({mode,setMode,email,setEmail,password,setPassword,fullName,setFullName,submit,loading,notice}:{mode:"login"|"register";setMode:(v:"login"|"register")=>void;email:string;setEmail:(v:string)=>void;password:string;setPassword:(v:string)=>void;fullName:string;setFullName:(v:string)=>void;submit:(e:React.FormEvent)=>void;loading:boolean;notice:Notice|null}) {
  return <div className="auth-layout"><div className="auth-visual"><div className="auth-brand"><div className="brand-mark"><GraduationCap size={22}/></div><strong>classroom<span>.</span></strong></div><div className="auth-visual-copy"><div className="hero-pill"><span/> THE CLASSROOM, CONNECTED</div><h1>Better learning<br/>starts <em>together.</em></h1><p>One thoughtful space for teachers to guide, students to grow, and classrooms to thrive.</p><div className="auth-illustration"><div className="auth-card card-a"><CheckCircle2 size={17}/> Assignment completed</div><div className="auth-card card-b"><Users size={17}/> Your class is in sync</div><div className="auth-book"><BookOpen size={54}/><Sparkles size={20}/></div></div></div><div className="auth-visual-foot">A little more clarity. A lot more learning.</div></div><div className="auth-form-side"><form className="auth-form" onSubmit={submit}><div className="eyebrow">WELCOME TO YOUR WORKSPACE</div><h2>{mode==="login"?"Welcome back":"Create your account"}</h2><p>{mode==="login"?"Sign in to pick up where your classroom left off.":"Start bringing your classroom together."}</p>{notice&&<div className={`notice ${notice.kind}`}>{notice.text}</div>}{mode==="register"&&<label>Full name<input required minLength={2} value={fullName} onChange={e=>setFullName(e.target.value)} placeholder="Your name"/></label>}<label>Email address<input required type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@school.com"/></label><label>Password<input required minLength={mode==="register"?12:1} type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder={mode==="register"?"At least 12 characters":"Enter your password"}/>{mode==="register"&&<small className="field-hint">Use at least 12 characters.</small>}</label><button className="primary-button auth-submit" disabled={loading}>{loading?"Please wait…":mode==="login"?"Sign in":"Create account"}<ArrowRight size={16}/></button><div className="auth-switch">{mode==="login"?"New to Classroom Companion?":"Already have an account?"} <button type="button" onClick={()=>setMode(mode==="login"?"register":"login")}>{mode==="login"?"Create an account":"Sign in"}</button></div><div className="secure-note"><ShieldCheck size={15}/> Your classroom data stays private and secure.</div></form></div></div>;
}

export default App;