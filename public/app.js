/* ═══════════════════════════════════════════════
   BARITA WEALTH ADVISOR — app.js
   Firebase Auth + Firestore + Flask backend
═══════════════════════════════════════════════ */

// ─── FIREBASE CONFIG ─────────────────────────────────────
const FIREBASE_CONFIG = {
  apiKey: "AIzaSyCYCE51wwDyxJ93Md7-SB3Vu0MouAkmupE",
  authDomain: "barita-soc-team-c.firebaseapp.com",
  projectId: "barita-soc-team-c",
  storageBucket: "barita-soc-team-c.firebasestorage.app",
  messagingSenderId: "363840368061",
  appId: "1:363840368061:web:d9c69645015d196e3236d4",
  measurementId: "G-D4E0HQSSFS"
};

// ─── BACKEND URL — Shar remember to replace with the Render/Railway URL after deploying ───────
// For local testing: const BACKEND_URL = "http://localhost:5000";
const BACKEND_URL = "http://localhost:5000";

// ─── FIREBASE IMPORTS ─────────────────────────────────────────────────────────
import { initializeApp }                              from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth, onAuthStateChanged, signOut,
         GoogleAuthProvider, signInWithPopup,
         signInWithEmailAndPassword,
         createUserWithEmailAndPassword,
         updateProfile, sendPasswordResetEmail }      from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";
import { getFirestore, doc, setDoc, getDoc,
         collection, addDoc, query, orderBy,
         limit, getDocs, serverTimestamp }            from "https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js";

const app  = initializeApp(FIREBASE_CONFIG);
const auth = getAuth(app);
const db   = getFirestore(app);

// ─── STATE ────────────────────────────────────────────────────────────────────
const state = {
  user:        null,
  firebaseToken: null,
  answers:     {},
  qStep:       0,
  report:      null,
  chatHistory: [],
  currentView: 'dashboard',
  isRegister:  false,
};

// ─── QUESTIONNAIRE DEFINITION ─────────────────────────────────────────────────
// Each section has: id, title, questions[]
// Each question: id, text, type (single|multi|text|textarea), options[], conditional?
const SECTIONS = [
  // PAGE 1: Profile
  {
    id: 'profile', title: 'Your Profile',
    questions: [
      { id: 'first_name', text: 'First Name', type: 'text', placeholder: 'e.g. Jane' },
      { id: 'last_name',  text: 'Last Name',  type: 'text', placeholder: 'e.g. Smith' },
      { id: 'age',        text: 'Age',        type: 'text', placeholder: 'e.g. 28' },
    ],
  },
  // PAGE 2: Background
  {
    id: 'background', title: 'Your Background',
    questions: [
      {
        id: 'knowledge_level', text: 'How much do you know about investing?', type: 'single',
        options: ["I'm completely new to investing", 'I have basic knowledge but no real experience', "I've been learning and have some experience", 'I have a lot of investing experience'],
      },
      {
        id: 'employment_status', text: 'What is your employment status?', type: 'single',
        options: ['Salaried employee', 'Self-employed / business owner', 'Part-time / contract', 'Unemployed', 'Retired'],
      },
      {
        id: 'pay_frequency', text: 'How often do you get paid?', type: 'single',
        options: ['Monthly', 'Weekly', 'Commission-based', 'Self-employed (irregular)'],
      },
    ],
  },
  // PAGE 3: Dependents
  {
    id: 'dependents', title: 'Financial Dependents',
    questions: [
      {
        id: 'dependents', text: 'Do you have financial dependents?', type: 'single',
        options: ['None', '1-2 children', '3+ children', 'Elderly parents', 'Children + parents', 'Other dependents'],
      },
    ],
  },
  // PAGE 4: Existing Investments
  {
    id: 'existing_investments', title: 'Existing Investments',
    questions: [
      {
        id: 'other_investments', text: 'Do you hold investments or pensions elsewhere?', type: 'multi',
        hint: 'Select all that apply',
        options: ['No other investments', 'Local stocks / bonds', 'Pension / NIS', 'Foreign investments', 'Real estate'],
      },
    ],
  },
  // PAGE 5: Tax Residency
  {
    id: 'tax', title: 'Tax Residency',
    questions: [
      {
        id: 'tax_residency', text: 'In which country are you a tax resident?', type: 'multi',
        hint: 'Select all that apply',
        options: ['Jamaica only', 'USA', 'UK', 'Canada', 'Other'],
      },
    ],
  },
  // PAGE 6: Financial Goals
  {
    id: 'goals', title: 'Financial Goals',
    questions: [
      {
        id: 'primary_goal', text: 'What is your primary financial goal?', type: 'single',
        options: ['Wealth accumulation / growth', 'Retirement planning', 'Education funding', 'Property purchase', 'Income generation', 'Capital preservation', 'Emergency fund building'],
      },
      {
        id: 'goal_priority', text: 'How would you describe the priority of this goal?', type: 'single',
        options: ['Essential - I must achieve this', 'Aspirational - I would like to achieve this'],
      },
      {
        id: 'withdrawal_time', text: 'Over the next 2 years, how much do you expect to withdraw from this portfolio?', type: 'single',
        options: ['No withdrawals', 'Less than 10%', '10-25%', 'More than 25%'],
      },
    ],
  },
  // PAGE 7: Risk Reaction
  {
    id: 'risk_reaction', title: 'Risk Reaction',
    questions: [
      {
        id: 'drop_reaction', text: 'How would you react if your investment dropped by 20%?', type: 'single',
        options: ['Sell everything to avoid further losses', 'Sell some to reduce losses', 'Wait for recovery', 'Invest more at lower prices'],
      },
    ],
  },
  // PAGE 8: Risk Profile
  {
    id: 'risk_profile', title: 'Risk Profile',
    questions: [
      {
        id: 'risk_relationship', text: 'Which best describes your relationship with investment risk?', type: 'single',
        options: ["I'm okay with small changes, but big losses stress me", 'I understand ups and downs and stay calm', "I'm comfortable with big risks and see drops as opportunities", 'I worry a lot about losing money'],
      },
      {
        id: 'loss_vs_gain', text: 'Which outcome would upset you more?', type: 'single',
        options: ['Missing a 20% gain', 'Suffering a 20% loss'],
      },
      {
        id: 'performance_benchmark', text: 'When reviewing your portfolio, what do you mainly compare it to?', type: 'single',
        options: ['The amount I originally invested', 'The overall increase in value (JMD gains)', 'My expected return', 'A market index', 'The rate of inflation'],
      },
      {
        id: 'max_loss', text: 'What is the maximum annual loss you could tolerate without changing strategy?', type: 'single',
        options: ['Up to 10%', 'Up to 20%', 'Up to 40%', 'More than 40%'],
      },
    ],
  },
  // PAGE 9: Financial Resilience
  {
    id: 'resilience', title: 'Financial Resilience',
    questions: [
      {
        id: 'income_loss_runway', text: 'If you lost your primary income, how long could you maintain your lifestyle without touching investments?', type: 'single',
        options: ['Less than 3 months', '3-6 months', '6-12 months', '1-2 years', 'More than 2 years'],
      },
      {
        id: 'debt_situation', text: 'What best describes your current debt situation?', type: 'single',
        options: ['Debt-free', 'Minor debt', 'Moderate debt', 'Significant debt'],
      },
    ],
  },
  // PAGE 10: Currency
  {
    id: 'currency', title: 'Currency Profile',
    questions: [
      {
        id: 'earn_currency', text: 'In what currency do you primarily earn?', type: 'single',
        options: ['JMD only', 'USD only', 'Mostly JMD', 'Mostly USD', 'Equal amounts of JMD and USD'],
      },
      {
        id: 'spend_currency', text: 'In what currency do you primarily spend?', type: 'single',
        options: ['JMD only', 'USD only', 'Mostly JMD', 'Mostly USD', 'Equal amounts of JMD and USD'],
      },
      {
        id: 'usd_liabilities', text: 'Do you have USD-denominated liabilities?', type: 'single',
        options: ['None', 'Under USD $10K', 'USD $10K-$50K', 'USD $50K-$200K', 'Over USD $200K'],
      },
      {
        id: 'inflation_impact', text: 'How much does JMD inflation affect your cost of living?', type: 'single',
        options: ['Not sure', 'Minimal', 'Moderate', 'Significant', 'Severe'],
      },
    ],
  },
  // PAGE 11: Portfolio Management
  {
    id: 'management', title: 'Portfolio Management',
    questions: [
      {
        id: 'review_frequency', text: 'How often should your portfolio be reviewed and rebalanced?', type: 'single',
        options: ['Monthly', 'Quarterly', 'Semi-annually', 'Annually', 'Only when needed'],
      },
      {
        id: 'market_adjustment', text: 'Are you open to adjusting your portfolio based on market conditions?', type: 'single',
        options: ['No - keep it fixed', 'Yes - small changes', 'Yes - moderate changes', 'Yes - fully active'],
      },
      {
        id: 'inflation_protection', text: 'Do you want inflation protection in your portfolio?', type: 'single',
        options: ['Yes - strong focus', 'Somewhat', 'Not necessary', 'Not sure'],
      },
      {
        id: 'invest_style', text: 'What is your preferred investment style?', type: 'single',
        options: ['Fully passive', 'Mostly passive', 'Balanced', 'Mostly active', 'Fully active'],
      },
      {
        id: 'involvement_level', text: 'How involved do you want to be in decisions?', type: 'single',
        options: ['Hands-off', 'Consulted on major changes', 'Approve major decisions', 'Fully involved'],
      },
    ],
  },
];
// ─── HELPERS ──────────────────────────────────────────────────────────────────
const $  = id => document.getElementById(id);
const el = (tag, cls = '', html = '') => { const e = document.createElement(tag); if (cls) e.className = cls; if (html) e.innerHTML = html; return e; };
const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

function switchView(view) {
  state.currentView = view;
  document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  const titles = { dashboard: 'Dashboard', questionnaire: 'Questionnaire', portfolio: 'My Portfolio', advisor: '🐻 Barita', reports: 'Reports' };
  $('topbar-title').textContent = titles[view] || view;
  renderView(view);
}

// ─── AUTH ──────────────────────────────────────────────────────────────────────
onAuthStateChanged(auth, async user => {
  if (user) {
    state.user = user;
    state.firebaseToken = await user.getIdToken();
    // Refresh token periodically
    setInterval(async () => { state.firebaseToken = await user.getIdToken(true); }, 50 * 60 * 1000);

    $('screen-login').classList.add('hidden');
    $('screen-app').classList.remove('hidden');

    const name = user.displayName || user.email.split('@')[0];
    const initial = name[0].toUpperCase();
    $('sidebar-name').textContent  = name;
    $('sidebar-email').textContent = user.email;
    $('sidebar-avatar').textContent = initial;
    $('topbar-avatar').textContent  = initial;

    await loadSession();
    switchView('dashboard');
  } else {
    state.user = null;
    $('screen-app').classList.add('hidden');
    $('screen-login').classList.remove('hidden');
  }
});

function setLoginError(msg) { $('login-error-text').textContent = msg; $('login-error').classList.remove('hidden'); }
function clearLoginError()  { $('login-error').classList.add('hidden'); }

async function handleGoogleSignIn() {
  clearLoginError();
  try {
    await signInWithPopup(auth, new GoogleAuthProvider());
  } catch(e) {
    if (e.code !== 'auth/popup-closed-by-user') setLoginError('Google sign-in failed: ' + e.message);
  }
}

async function handleEmailAuth() {
  clearLoginError();
  const email = $('input-email').value.trim();
  const pass  = $('input-password').value;
  if (!email || !pass) { setLoginError('Please enter email and password.'); return; }
  if (pass.length < 6) { setLoginError('Password must be at least 6 characters.'); return; }

  $('btn-email-auth').disabled = true;
  $('btn-email-text').textContent = state.isRegister ? 'Creating…' : 'Signing in…';
  $('btn-email-arrow').classList.add('hidden');
  $('btn-email-spinner').classList.remove('hidden');

  try {
    if (state.isRegister) {
      const name    = $('input-name').value.trim();
      const confirm = $('input-confirm').value;
      if (!name)          { setLoginError('Please enter your full name.');    throw new Error(); }
      if (pass !== confirm){ setLoginError('Passwords do not match.');         throw new Error(); }
      const cred = await createUserWithEmailAndPassword(auth, email, pass);
      await updateProfile(cred.user, { displayName: name });
    } else {
      await signInWithEmailAndPassword(auth, email, pass);
    }
  } catch(e) {
    const msgs = {
      'auth/user-not-found':       'No account found with this email.',
      'auth/wrong-password':       'Incorrect password.',
      'auth/email-already-in-use': 'This email is already registered.',
      'auth/invalid-email':        'Please enter a valid email.',
      'auth/too-many-requests':    'Too many attempts — please wait.',
    };
    if (e.code) setLoginError(msgs[e.code] || e.message);
    $('btn-email-auth').disabled = false;
    $('btn-email-text').textContent = state.isRegister ? 'Create Account' : 'Sign In';
    $('btn-email-arrow').classList.remove('hidden');
    $('btn-email-spinner').classList.add('hidden');
  }
}

function toggleRegisterMode() {
  state.isRegister = !state.isRegister;
  $('register-fields').classList.toggle('hidden', !state.isRegister);
  $('register-confirm').classList.toggle('hidden', !state.isRegister);
  $('auth-title').textContent     = state.isRegister ? 'Create your account' : 'Sign in to your account';
  $('auth-sub').textContent       = state.isRegister ? 'Join the Barita SOC 2026 platform.' : 'Welcome back. Enter your details below.';
  $('toggle-label').textContent   = state.isRegister ? 'Already have an account?' : "Don't have an account?";
  $('btn-toggle-mode').textContent= state.isRegister ? 'Sign in instead' : 'Create one';
  $('btn-email-text').textContent = state.isRegister ? 'Create Account' : 'Sign In';
  clearLoginError();
}

window.handleSignOut = async () => {
  state.answers = {}; state.report = null; state.chatHistory = [];
  await signOut(auth);
};

// ─── FIRESTORE ─────────────────────────────────────────────────────────────────
async function saveSession() {
  if (!state.user) return;
  try {
    await setDoc(doc(db, 'sessions', state.user.uid), {
      answers:   state.answers,
      report:    state.report ? { profile: state.report.profile, metrics: state.report.metrics, profile_label: state.report.profile_label } : null,
      updatedAt: serverTimestamp(),
    });
  } catch(e) { console.warn('Save failed:', e.message); }
}

async function loadSession() {
  if (!state.user) return;
  try {
    const snap = await getDoc(doc(db, 'sessions', state.user.uid));
    if (snap.exists()) {
      const d = snap.data();
      if (d.answers) state.answers = d.answers;
      if (d.report)  state.report  = d.report;
    }
  } catch(e) { console.warn('Load failed:', e.message); }
}

async function loadReportHistory() {
  if (!state.user) return [];
  try {
    const q    = query(collection(db, 'users', state.user.uid, 'reports'), orderBy('createdAt','desc'), limit(10));
    const snap = await getDocs(q);
    return snap.docs.map(d => ({ id: d.id, ...d.data() }));
  } catch(e) { return []; }
}

// ─── BACKEND CALLS ─────────────────────────────────────────────────────────────
async function callBackend(endpoint, body) {
  const token = state.firebaseToken || await state.user.getIdToken();
  const res   = await fetch(`${BACKEND_URL}${endpoint}`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
    body:    JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Backend error ${res.status}: ${await res.text()}`);
  return res.json();
}

async function downloadPDF(reportId) {
  const token = state.firebaseToken || await state.user.getIdToken();
  const res   = await fetch(`${BACKEND_URL}/generate_report`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
    body:    JSON.stringify({ answers: state.answers, report: state.report, report_id: reportId }),
  });
  if (!res.ok) { alert('Failed to generate PDF. Please try again.'); return; }
  const blob = await res.blob();
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  const name = state.user?.displayName || 'Client';
  a.href = url; a.download = `Barita_Portfolio_Report_${name.replace(/\s+/g,'_')}.pdf`;
  a.click(); URL.revokeObjectURL(url);
}

// ─── VIEWS ────────────────────────────────────────────────────────────────────
function renderView(view) {
  const area = $('view-area');
  area.innerHTML = '';
  if      (view === 'dashboard')     renderDashboard(area);
  else if (view === 'questionnaire') renderQuestionnaireView(area);
  else if (view === 'portfolio')     renderPortfolioView(area);
  else if (view === 'advisor')       renderAdvisorView(area);
  else if (view === 'reports')       renderReportsView(area);
}

// ── DASHBOARD ──
function renderDashboard(area) {
  const name    = state.user?.displayName || state.user?.email?.split('@')[0] || 'there';
  const profile = state.report?.profile || null;
  const label   = state.report?.profile_label || null;
  const done    = Object.keys(state.answers).length > 5;

  area.innerHTML = `
    <!-- Welcome banner -->
    <div class="dash-welcome">
      <div>
        <div class="dash-welcome-h">Welcome back, ${esc(name.split(' ')[0])} 👋</div>
        <p class="dash-welcome-p">${done
          ? `Your <strong style="color:var(--teal-light)">${esc(profile)}</strong> portfolio is ready. View your allocation and download your report.`
          : 'Complete the risk profiling questionnaire to get your personalised portfolio recommendation.'
        }</p>
      </div>
      <button class="dash-welcome-btn" onclick="${done ? "switchView('portfolio')" : "openQuestionnaire()"}">
        ${done ? '📊 View Portfolio' : '📋 Start Questionnaire'}
      </button>
    </div>

    <!-- Stat cards -->
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-card-label"><div class="stat-card-icon teal">📋</div>Questionnaire</div>
        <div class="stat-card-val">${done ? '100%' : Math.round((Object.keys(state.answers).length / 15) * 100) + '%'}</div>
        <div class="stat-card-sub">${done ? 'Completed' : 'In progress'}</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-label"><div class="stat-card-icon teal">🎯</div>Risk Profile</div>
        <div class="stat-card-val" style="font-size:18px">${profile ? `<span class="profile-badge ${profile.toLowerCase()}">${profile}</span>` : '—'}</div>
        <div class="stat-card-sub">${label || 'Not yet assessed'}</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-label"><div class="stat-card-icon green">📈</div>Expected Return</div>
        <div class="stat-card-val ${profile ? 'green' : ''}">${state.report?.metrics?.expected_return || '—'}</div>
        <div class="stat-card-sub">Annualised estimate</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-label"><div class="stat-card-icon blue">📄</div>Reports</div>
        <div class="stat-card-val">${done ? '1' : '0'}</div>
        <div class="stat-card-sub">${done ? '<span class="badge-up">↑ Ready to download</span>' : 'Complete questionnaire first'}</div>
      </div>
    </div>

    ${done && state.report?.allocations ? renderMiniAllocation() : `
    <div class="panel">
      <div class="empty-state">
        <div class="empty-icon">📋</div>
        <div class="empty-h">Start Your Risk Profile</div>
        <p class="empty-p">Answer 12 sections about your goals, risk tolerance, and financial situation to get a personalised portfolio.</p>
        <button class="btn-action" onclick="openQuestionnaire()">Begin Questionnaire →</button>
      </div>
    </div>
    `}
  `;
}

function renderMiniAllocation() {
  const allocs = state.report.allocations || [];
  return `
    <div class="three-col">
      <div class="panel">
        <div class="panel-header">
          <div><div class="panel-title">Portfolio Allocation</div><div class="panel-sub">Recommended asset mix</div></div>
          <button class="btn-dl" onclick="switchView('portfolio')">View full →</button>
        </div>
        <div class="panel-body">
          <div class="alloc-table" id="mini-alloc"></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header"><div class="panel-title">Performance Metrics</div></div>
        <div class="panel-body">
          ${renderMetrics()}
        </div>
      </div>
    </div>
  `;
}

function renderMetrics() {
  const m = state.report?.metrics || {};
  return `
    <div style="display:flex;flex-direction:column;gap:14px">
      <div><div class="stat-card-label">Expected Return</div><div style="font-family:var(--font-display);font-size:22px;font-weight:700;color:var(--green)">${m.expected_return || '—'}</div></div>
      <div class="divider"></div>
      <div><div class="stat-card-label">Volatility</div><div style="font-family:var(--font-display);font-size:22px;font-weight:700;color:var(--red)">${m.volatility || '—'}</div></div>
      <div class="divider"></div>
      <div><div class="stat-card-label">Sharpe Ratio</div><div style="font-family:var(--font-display);font-size:22px;font-weight:700;color:var(--teal)">${m.sharpe_ratio || '—'}</div></div>
    </div>
  `;
}

// ── QUESTIONNAIRE VIEW (just a prompt to open modal) ──
function renderQuestionnaireView(area) {
  const done = Object.keys(state.answers).length > 5;
  area.innerHTML = `
    <div class="panel" style="max-width:640px;margin:0 auto">
      <div class="panel-header"><div class="panel-title">Investment Risk Profiling Questionnaire</div></div>
      <div class="panel-body">
        <p style="font-size:14px;color:var(--text-muted);line-height:1.7;margin-bottom:20px">
          Understanding your risk profile will help us make investment recommendations that are suitable for you.
          This covers 12 sections: experience, goals, time horizon, risk tolerance, financial situation, liquidity,
          income needs, currency exposure, economic sensitivities, cost sensitivity, asset restrictions, and investment style.
        </p>
        ${done ? `
          <div style="background:var(--green-bg);border:1px solid rgba(16,185,129,0.25);border-radius:var(--radius);padding:14px 18px;margin-bottom:20px;font-size:14px;color:var(--green);font-weight:500">
            ✓ Questionnaire completed. Your portfolio has been generated.
          </div>` : ''}
        <button class="btn-action" onclick="openQuestionnaire()">
          ${done ? '✏️ Retake Questionnaire' : '📋 Begin Questionnaire →'}
        </button>
      </div>
    </div>
  `;
}

// ── PORTFOLIO VIEW ──
function renderPortfolioView(area) {
  if (!state.report || !state.report.allocations) {
    area.innerHTML = `
      <div class="panel">
        <div class="empty-state">
          <div class="empty-icon">📊</div>
          <div class="empty-h">No Portfolio Yet</div>
          <p class="empty-p">Complete the questionnaire to generate your personalised portfolio.</p>
          <button class="btn-action" onclick="openQuestionnaire()">Start Questionnaire →</button>
        </div>
      </div>`;
    return;
  }

  const { profile, profile_label, allocations, metrics, risk_breakdown } = state.report;
  const name = state.user?.displayName?.split(' ')[0] || 'Investor';

  // Simplified explanations for metrics
  const metaExplain = {
    expected_return: 'This is the average annual growth we expect your money to make. For example, if you invest $100,000 and the expected return is 8%, you could expect roughly $8,000 in growth per year.',
    volatility: 'This measures how much your portfolio value might go up or down on any given year. A lower number means a smoother ride; a higher number means bigger swings — but also bigger potential gains.',
    sharpe_ratio: 'This tells you how much reward you are getting for the risk you are taking. A higher number is better. Above 1.0 is considered good — it means the returns are worth the risk.'
  };

  // Risk-o-meter level
  const riskLevels = { conservative: 1, moderate: 2, aggressive: 3 };
  const riskLevel = riskLevels[profile?.toLowerCase()] || 2;
  const riskColors = { conservative: '#10B981', moderate: '#F59E0B', aggressive: '#EF4444' };
  const riskColor = riskColors[profile?.toLowerCase()] || '#F59E0B';
  const riskDescriptions = {
    conservative: 'You prefer safety and stability. Your portfolio focuses on protecting what you have while earning steady, predictable returns. Think of it like keeping your money in a very well-managed savings plan.',
    moderate: 'You are comfortable with some ups and downs in exchange for better long-term growth. Your portfolio balances safety and growth - like a mix of a savings account and stocks.',
    aggressive: 'You are focused on maximum long-term growth and can handle short-term drops without panic. Your portfolio takes more risk for the chance of higher rewards over time.'
  };

  // Simplified asset category descriptions
  const categoryDescriptions = {
    'Cash':         '💵 Think of this like a high-interest savings account. Very safe, easy to access, but lower returns.',
    'Fixed Income': '🏛️ These are loans you give to governments or companies. They pay you regular interest - like a steady paycheck from your investment.',
    'Equity':       '📈 These are small ownership stakes in companies. They can grow a lot over time but may drop in the short term.',
    'Real Estate':  '🏠 Investing in property through a fund. Earns rental-style income and tends to protect against inflation.',
    'Alternatives': '🎯 Non-traditional investments like hedge funds or private assets that behave differently from stocks and bonds — great for diversification.'
  };

  // Build superclass grouping
  const superGroups = {};
  allocations.forEach(a => {
    const sc = a.superClass || a.asset_class || a['class'] || 'Other';
    if (!superGroups[sc]) superGroups[sc] = { total: 0, items: [] };
    superGroups[sc].total += parseFloat(a.pct) || 0;
    superGroups[sc].items.push(a);
  });

  const chartColors = ['#0BB8A9','#3B82F6','#F59E0B','#10B981','#EF4444','#8B5CF6','#EC4899','#06B6D4','#84CC16','#F97316','#6366F1','#14B8A6'];

  area.innerHTML = `
    <!-- Header -->
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;flex-wrap:wrap;gap:12px">
      <div>
        <h2 style="font-family:var(--font-display);font-size:22px;font-weight:700;color:var(--text);margin-bottom:4px">
          ${esc(name)}'s Investment Portfolio
          <span class="profile-badge ${profile.toLowerCase()}" style="margin-left:10px;font-size:13px">${esc(profile)}</span>
        </h2>
        <p style="font-size:13px;color:var(--text-muted)">${esc(profile_label || 'Personalised portfolio based on your risk profile')}</p>
      </div>
      <button class="btn-dl" id="btn-dl-main" style="padding:10px 22px;font-size:13px">⬇ Download Full Report</button>
    </div>

    <!-- SECTION 1: What This Means For You -->
    <div class="panel" style="margin-bottom:20px;border-left:4px solid ${riskColor}">
      <div class="panel-header">
        <div><div class="panel-title">🙋 What Does This Mean For You?</div><div class="panel-sub">Plain English explanation of your portfolio</div></div>
      </div>
      <div class="panel-body">
        <p style="font-size:15px;line-height:1.75;color:var(--text)">${riskDescriptions[profile?.toLowerCase()] || ''}</p>
      </div>
    </div>

    <!-- SECTION 2: Risk-O-Meter + Key Stats -->
    <div class="two-col" style="margin-bottom:20px">

      <!-- Risk-O-Meter -->
      <div class="panel">
        <div class="panel-header"><div class="panel-title">⚡ Your Risk Level</div></div>
        <div class="panel-body" style="text-align:center">
          <div style="position:relative;margin:0 auto 16px;width:200px;height:110px;overflow:hidden">
            <canvas id="risk-gauge" width="200" height="110"></canvas>
          </div>
          <div style="font-family:var(--font-display);font-size:22px;font-weight:700;color:${riskColor};margin-bottom:6px">${esc(profile)}</div>
          <div style="font-size:13px;color:var(--text-muted);line-height:1.6">
            ${riskLevel === 1 ? 'Low risk · Steady &amp; stable' : riskLevel === 2 ? 'Medium risk · Balanced growth' : 'Higher risk · Maximum growth potential'}
          </div>
          <div style="display:flex;justify-content:space-between;margin-top:16px;padding-top:16px;border-top:1px solid var(--border)">
            <div style="text-align:center"><div style="font-size:11px;color:var(--text-faint);margin-bottom:4px">CONSERVATIVE</div><div style="width:12px;height:12px;border-radius:50%;background:#10B981;margin:0 auto"></div></div>
            <div style="text-align:center"><div style="font-size:11px;color:var(--text-faint);margin-bottom:4px">MODERATE</div><div style="width:12px;height:12px;border-radius:50%;background:#F59E0B;margin:0 auto"></div></div>
            <div style="text-align:center"><div style="font-size:11px;color:var(--text-faint);margin-bottom:4px">AGGRESSIVE</div><div style="width:12px;height:12px;border-radius:50%;background:#EF4444;margin:0 auto"></div></div>
          </div>
        </div>
      </div>

      <!-- Key Metrics with tooltips -->
      <div class="panel">
        <div class="panel-header"><div class="panel-title">📊 Key Numbers</div><div class="panel-sub">Hover each metric to learn what it means</div></div>
        <div class="panel-body" style="display:flex;flex-direction:column;gap:0">
          ${[
            { key: 'expected_return', label: 'Expected Annual Return', val: metrics.expected_return, color: 'var(--green)', icon: '📈' },
            { key: 'volatility',      label: 'Volatility (Risk Level)', val: metrics.volatility,      color: 'var(--red)',   icon: '〰️' },
            { key: 'sharpe_ratio',    label: 'Sharpe Ratio',            val: metrics.sharpe_ratio,    color: 'var(--teal)',  icon: '⚖️' },
          ].map((m, i) => `
            <div class="metric-tooltip-wrap" style="padding:14px 0;${i < 2 ? 'border-bottom:1px solid var(--border);' : ''}position:relative;cursor:help"
                 onmouseenter="this.querySelector('.metric-tip').style.display='block'"
                 onmouseleave="this.querySelector('.metric-tip').style.display='none'">
              <div style="display:flex;align-items:center;gap:10px">
                <span style="font-size:20px">${m.icon}</span>
                <div style="flex:1">
                  <div style="font-size:12px;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:0.04em">${m.label} <span style="color:var(--teal-border);font-size:11px">ⓘ</span></div>
                  <div style="font-family:var(--font-display);font-size:26px;font-weight:700;color:${m.color}">${esc(m.val || '—')}</div>
                </div>
              </div>
              <div class="metric-tip" style="display:none;position:absolute;left:0;right:0;bottom:calc(100% + 4px);background:var(--navy);color:white;border-radius:8px;padding:10px 14px;font-size:12px;line-height:1.6;z-index:10;box-shadow:0 4px 16px rgba(0,0,0,0.2)">
                ${metaExplain[m.key]}
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    </div>

    <!-- SECTION 3: Donut Chart + Asset Breakdown -->
    <div class="two-col" style="margin-bottom:20px">

      <!-- Donut chart -->
      <div class="panel">
        <div class="panel-header"><div class="panel-title">🍩 Where Is My Money Going?</div><div class="panel-sub">Visual breakdown of your allocation</div></div>
        <div class="panel-body" style="display:flex;gap:20px;align-items:center;flex-wrap:wrap">
          <canvas id="alloc-donut" width="180" height="180" style="flex-shrink:0"></canvas>
          <div id="donut-legend" style="flex:1;min-width:140px;display:flex;flex-direction:column;gap:8px"></div>
        </div>
      </div>

      <!-- Asset category explanations -->
      <div class="panel">
        <div class="panel-header"><div class="panel-title">📚 Asset Types Explained</div><div class="panel-sub">What each category actually is</div></div>
        <div class="panel-body" style="display:flex;flex-direction:column;gap:12px">
          ${Object.entries(categoryDescriptions).map(([cat, desc]) => {
            const inPortfolio = allocations.some(a => (a.superClass || a.asset_class || a['class'] || '') === cat || (a.superClass || a.asset_class || a['class'] || '').includes(cat));
            return `<div style="padding:12px 14px;border-radius:8px;background:${inPortfolio ? 'var(--teal-glow)' : 'var(--surface-2)'};border:1px solid ${inPortfolio ? 'var(--teal-border)' : 'var(--border)'}">
              <div style="font-size:14px;font-weight:600;color:var(--text);margin-bottom:4px">${cat} ${inPortfolio ? '<span style="font-size:11px;color:var(--teal);font-weight:700">✓ IN YOUR PORTFOLIO</span>' : ''}</div>
              <div style="font-size:13px;color:var(--text-muted);line-height:1.6">${desc}</div>
            </div>`;
          }).join('')}
        </div>
      </div>
    </div>

    <!-- SECTION 4: Full allocation bar chart -->
    <div class="panel" style="margin-bottom:20px">
      <div class="panel-header"><div class="panel-title">📋 Your Full Allocation</div><div class="panel-sub">Each asset in plain English</div></div>
      <div class="panel-body">
        <canvas id="alloc-bar-chart" height="80" style="margin-bottom:20px"></canvas>
        <div id="alloc-cards" style="display:flex;flex-direction:column;gap:10px"></div>
      </div>
    </div>

    <!-- SECTION 5: Growth Projection -->
    <div class="panel" style="margin-bottom:20px">
      <div class="panel-header">
        <div><div class="panel-title">📈 How Could Your Money Grow?</div><div class="panel-sub">Hypothetical 10-year projection based on your portfolio's expected return</div></div>
      </div>
      <div class="panel-body">
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;line-height:1.65">
          This chart shows what could happen to <strong>$100,000</strong> invested in your portfolio over 10 years.
          The middle line is the expected outcome. The shaded area shows the range of realistic outcomes based on your portfolio's volatility.
          <em>This is illustrative only — actual returns will vary.</em>
        </p>
        <canvas id="growth-chart" height="70"></canvas>
      </div>
    </div>

    <!-- SECTION 6: Your Profile Summary -->
    <div class="panel" style="margin-bottom:20px">
      <div class="panel-header"><div class="panel-title">👤 Your Investment Profile Summary</div><div class="panel-sub">Key facts used to build your portfolio</div></div>
      <div class="panel-body" style="padding:0">
        <table class="fi-table">
          <thead><tr><th>What We Looked At</th><th>Your Answer</th><th>What It Means</th></tr></thead>
          <tbody>
            <tr><td>Primary Goal</td><td>${esc(state.answers.primary_goal || '—')}</td><td style="font-size:12px;color:var(--text-muted)">The main thing you want your money to do for you</td></tr>
            <tr><td>Investment Horizon</td><td>${esc(state.answers.withdrawal_time || '—')}</td><td style="font-size:12px;color:var(--text-muted)">How soon you might need this money back</td></tr>
            <tr><td>Risk Reaction</td><td>${esc(state.answers.drop_reaction || '—')}</td><td style="font-size:12px;color:var(--text-muted)">How you would respond if markets dropped</td></tr>
            <tr><td>Max Loss Tolerance</td><td>${esc(state.answers.max_loss || '—')}</td><td style="font-size:12px;color:var(--text-muted)">The biggest loss you could handle without changing strategy</td></tr>
            <tr><td>Debt Situation</td><td>${esc(state.answers.debt_situation || '—')}</td><td style="font-size:12px;color:var(--text-muted)">Your current debt affects how much risk is appropriate</td></tr>
            <tr><td>Income Runway</td><td>${esc(state.answers.income_loss_runway || '—')}</td><td style="font-size:12px;color:var(--text-muted)">How long you could survive financially without your income</td></tr>
            <tr><td>Primary Currency</td><td>${esc(state.answers.earn_currency || '—')}</td><td style="font-size:12px;color:var(--text-muted)">Affects which instruments suit you best</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- SECTION 7: Key Risks -->
    <div class="panel" style="margin-bottom:20px">
      <div class="panel-header"><div class="panel-title">⚠️ Things To Keep In Mind</div><div class="panel-sub">Honest risks every investor should know about</div></div>
      <div class="panel-body">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          ${[
            { icon: '📉', title: 'Market ups and downs', desc: 'All investments can lose value in the short term. This is normal and expected — the key is staying patient.' },
            { icon: '💱', title: 'Currency risk', desc: 'Some assets in your portfolio are in USD. If the JMD strengthens, those returns could look smaller in local currency.' },
            { icon: '🏦', title: 'Interest rate changes', desc: 'When interest rates rise, bond (fixed income) prices typically fall. This affects the fixed income portion of your portfolio.' },
            { icon: '⏳', title: 'Time horizon matters', desc: 'This portfolio is built for your stated time horizon. Withdrawing early could lock in losses at the wrong time.' },
          ].map(r => `
            <div style="padding:14px;border-radius:10px;background:var(--amber-bg);border:1px solid rgba(245,158,11,0.2)">
              <div style="font-size:20px;margin-bottom:8px">${r.icon}</div>
              <div style="font-size:13px;font-weight:700;color:var(--text);margin-bottom:4px">${r.title}</div>
              <div style="font-size:12px;color:var(--text-muted);line-height:1.6">${r.desc}</div>
            </div>
          `).join('')}
        </div>
      </div>
    </div>
  `;

  // ── Draw Risk Gauge ──
  const gaugeCanvas = document.getElementById('risk-gauge');
  if (gaugeCanvas) {
    const ctx = gaugeCanvas.getContext('2d');
    const cx = 100, cy = 100, r = 80;
    // Background arc
    ctx.beginPath(); ctx.arc(cx, cy, r, Math.PI, 0); ctx.lineWidth = 18;
    const grad = ctx.createLinearGradient(20, 0, 180, 0);
    grad.addColorStop(0, '#10B981'); grad.addColorStop(0.5, '#F59E0B'); grad.addColorStop(1, '#EF4444');
    ctx.strokeStyle = grad; ctx.stroke();
    // Needle
    const angle = Math.PI + ((riskLevel - 1) / 2) * Math.PI;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + (r - 10) * Math.cos(angle), cy + (r - 10) * Math.sin(angle));
    ctx.lineWidth = 3; ctx.strokeStyle = '#1A2342'; ctx.lineCap = 'round'; ctx.stroke();
    ctx.beginPath(); ctx.arc(cx, cy, 6, 0, Math.PI * 2);
    ctx.fillStyle = '#1A2342'; ctx.fill();
  }

  // ── Draw Donut Chart ──
  const donutCanvas = document.getElementById('alloc-donut');
  if (donutCanvas && typeof Chart !== 'undefined') {
    new Chart(donutCanvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: allocations.map(a => a.ticker || a.label),
        datasets: [{ data: allocations.map(a => parseFloat(a.pct) || 0), backgroundColor: chartColors, borderWidth: 0, hoverOffset: 4 }]
      },
      options: { responsive: false, cutout: '65%', plugins: { legend: { display: false } } }
    });
    const legend = document.getElementById('donut-legend');
    allocations.forEach((a, i) => {
      const item = document.createElement('div');
      item.style.cssText = 'display:flex;align-items:center;gap:8px;font-size:12px';
      item.innerHTML = `<div style="width:10px;height:10px;border-radius:3px;flex-shrink:0;background:${chartColors[i % chartColors.length]}"></div>
        <span style="color:var(--text-muted);flex:1">${esc(a.label || a.ticker)}</span>
        <span style="font-weight:700;color:var(--text)">${a.pct}%</span>`;
      legend.appendChild(item);
    });
  }

  // ── Draw Bar Chart ──
  const barCanvas = document.getElementById('alloc-bar-chart');
  if (barCanvas && typeof Chart !== 'undefined') {
    new Chart(barCanvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: allocations.map(a => a.ticker || a.label),
        datasets: [{ data: allocations.map(a => parseFloat(a.pct) || 0), backgroundColor: chartColors, borderWidth: 0, borderRadius: 6 }]
      },
      options: {
        responsive: true, indexAxis: 'x',
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 11 } } },
          y: { grid: { color: 'rgba(0,0,0,0.05)' }, ticks: { callback: v => v + '%' } }
        }
      }
    });
  }

  // ── Allocation Cards ──
  const cardsEl = document.getElementById('alloc-cards');
  const assetPlainEnglish = {
    'Cash':         'Safe cash reserve — earns steady interest, always accessible.',
    'Fixed Income': 'Earns regular interest payments from governments or companies. Lower risk than stocks.',
    'Equity':       'Ownership in companies. Higher growth potential over time, but can be volatile short-term.',
    'Real Estate':  'Property investment through a fund. Earns income and grows with the property market.',
    'Alternatives': 'Non-traditional investments designed to diversify and reduce overall portfolio risk.',
    'Fund':         'A managed basket of multiple assets for built-in diversification.'
  };
  allocations.forEach((a, i) => {
    const sc = a.superClass || a.asset_class || a['class'] || 'Other';
    const plainEng = assetPlainEnglish[sc] || Object.entries(assetPlainEnglish).find(([k]) => sc.includes(k))?.[1] || 'A diversified investment instrument.';
    const card = document.createElement('div');
    card.style.cssText = 'display:flex;align-items:center;gap:14px;padding:14px 16px;border-radius:10px;background:var(--surface-2);border:1px solid var(--border)';
    card.innerHTML = `
      <div style="width:10px;height:40px;border-radius:5px;flex-shrink:0;background:${chartColors[i % chartColors.length]}"></div>
      <div style="flex:1;min-width:0">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:3px">
          <span style="font-weight:700;font-size:14px;color:var(--text)">${esc(a.label || a.ticker)}</span>
          <span style="font-size:11px;color:var(--text-faint);background:var(--border);padding:1px 7px;border-radius:10px">${esc(a.ticker || '')}</span>
          <span style="font-size:11px;color:var(--text-faint)">${esc(sc)}</span>
        </div>
        <div style="font-size:12px;color:var(--text-muted);line-height:1.5">${plainEng}${a.rationale ? ' ' + esc(a.rationale) : ''}</div>
      </div>
      <div style="text-align:right;flex-shrink:0">
        <div style="font-family:var(--font-display);font-size:20px;font-weight:700;color:${chartColors[i % chartColors.length]}">${a.pct}%</div>
        <div style="font-size:11px;color:var(--text-faint)">of portfolio</div>
      </div>
    `;
    cardsEl.appendChild(card);
  });
  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.querySelectorAll('.alloc-bar-inner').forEach(b => { b.style.width = b.dataset.pct + '%'; });
  }));

  // ── Growth Projection Chart ──
  const growthCanvas = document.getElementById('growth-chart');
  if (growthCanvas && typeof Chart !== 'undefined') {
    const retStr  = metrics.expected_return || '8%';
    const volStr  = metrics.volatility      || '10%';
    const ret = parseFloat(retStr) / 100 || 0.08;
    const vol = parseFloat(volStr) / 100 || 0.10;
    const years = [0,1,2,3,4,5,6,7,8,9,10];
    const base   = years.map(y => Math.round(100000 * Math.pow(1 + ret, y)));
    const upper  = years.map(y => Math.round(100000 * Math.pow(1 + ret + vol * 0.5, y)));
    const lower  = years.map(y => Math.round(100000 * Math.pow(1 + ret - vol * 0.5, y)));
    new Chart(growthCanvas.getContext('2d'), {
      type: 'line',
      data: {
        labels: years.map(y => 'Year ' + y),
        datasets: [
          { label: 'Optimistic', data: upper, borderColor: 'rgba(16,185,129,0.3)', backgroundColor: 'rgba(16,185,129,0.06)', borderDash: [4,4], fill: false, pointRadius: 0, tension: 0.4 },
          { label: 'Expected',   data: base,  borderColor: '#0BB8A9', backgroundColor: 'rgba(11,184,169,0.08)', fill: '-1', pointRadius: 3, tension: 0.4, borderWidth: 2.5 },
          { label: 'Conservative', data: lower, borderColor: 'rgba(239,68,68,0.3)', backgroundColor: 'rgba(239,68,68,0.06)', borderDash: [4,4], fill: false, pointRadius: 0, tension: 0.4 }
        ]
      },
      options: {
        responsive: true,
        plugins: { legend: { position: 'top', labels: { font: { size: 11 }, boxWidth: 20 } },
          tooltip: { callbacks: { label: ctx => ' $' + ctx.raw.toLocaleString() } } },
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: 'rgba(0,0,0,0.04)' }, ticks: { callback: v => '$' + (v/1000).toFixed(0) + 'K' } }
        }
      }
    });
  }

  document.getElementById('btn-dl-main')?.addEventListener('click', () => downloadPDF('latest'));
}

// ── AI ADVISOR VIEW ──
// ── BEAR ADVISOR VIEW ──
// Replaces the old plain-text AI Advisor with the full Barita bear chat experience
function renderAdvisorView(area) {
  const profile  = state.report?.behavioral_profile || state.report?.profile;
  const hasReport= !!(state.report && state.report.allocations);

  area.innerHTML = `
    <style>
      /* Bear advisor styles scoped to this view */
      .bear-chat-wrap { max-width: 760px; display: flex; flex-direction: column; height: calc(100vh - 180px); min-height: 500px; }
      .bear-chat-header { display:flex; align-items:center; justify-content:space-between; padding:18px 22px; background:var(--surface); border:1px solid var(--border); border-radius:16px 16px 0 0; box-shadow:0 1px 0 var(--border); }
      .bear-chat-header-left { display:flex; align-items:center; gap:12px; }
      .bear-avatar-lg { width:46px; height:46px; border-radius:50%; background:#FDF6EC; border:2px solid #FEF3C7; display:flex; align-items:center; justify-content:center; font-size:26px; box-shadow:0 2px 8px rgba(245,158,11,0.2); flex-shrink:0; }
      .bear-chat-name { font-family:'Plus Jakarta Sans',sans-serif; font-size:16px; font-weight:700; color:var(--text); }
      .bear-chat-sub  { font-size:12px; color:var(--text-muted); margin-top:2px; }
      .bear-online    { display:flex; align-items:center; gap:5px; font-size:11px; font-weight:600; color:var(--green); }
      .bear-online-dot{ width:7px; height:7px; border-radius:50%; background:var(--green); animation:pulse 2s infinite; }
      @keyframes pulse{ 0%,100%{opacity:1} 50%{opacity:0.4} }

      .bear-messages { flex:1; overflow-y:auto; padding:20px 22px; display:flex; flex-direction:column; gap:14px; background:var(--surface-2); border-left:1px solid var(--border); border-right:1px solid var(--border); }
      .bear-messages::-webkit-scrollbar { width:4px; }
      .bear-messages::-webkit-scrollbar-thumb { background:var(--border); border-radius:2px; }

      .bmsg-bear { display:flex; align-items:flex-start; gap:10px; animation:msgIn 0.35s cubic-bezier(0.22,1,0.36,1) both; }
      .bmsg-user { display:flex; justify-content:flex-end; animation:msgIn 0.3s ease both; }
      @keyframes msgIn{ from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }

      .bmsg-bear-av { width:34px; height:34px; border-radius:50%; background:#FDF6EC; border:1.5px solid #FEF3C7; display:flex; align-items:center; justify-content:center; font-size:18px; flex-shrink:0; }
      .bmsg-bear-bubble { background:var(--surface); border:1.5px solid var(--border); border-radius:18px 18px 18px 4px; padding:12px 16px; max-width:78%; font-size:14px; line-height:1.7; color:var(--text); box-shadow:0 1px 4px rgba(0,0,0,0.04); }
      .bmsg-bear-bubble strong { color:var(--teal); }
      .bmsg-user-bubble { background:var(--teal); color:white; border-radius:18px 18px 4px 18px; padding:11px 16px; max-width:72%; font-size:14px; line-height:1.65; box-shadow:0 4px 12px rgba(11,184,169,0.25); }

      .bear-options { display:flex; flex-direction:column; gap:7px; margin-left:44px; margin-top:4px; animation:msgIn 0.35s 0.05s ease both; }
      .bear-opt-btn { background:var(--surface); border:1.5px solid var(--border); border-radius:10px; padding:9px 16px; font-family:'DM Sans',sans-serif; font-size:13px; font-weight:500; color:var(--text); cursor:pointer; text-align:left; transition:all 0.18s; display:flex; align-items:center; gap:8px; }
      .bear-opt-btn:hover { border-color:var(--teal); background:var(--teal-glow,#E8FAF8); color:var(--teal); transform:translateX(3px); }
      .bear-opt-btn.selected { border-color:var(--teal); background:var(--teal-glow,#E8FAF8); color:var(--teal); font-weight:600; }
      .opt-check { width:16px; height:16px; border-radius:50%; border:1.5px solid var(--border); display:flex; align-items:center; justify-content:center; font-size:9px; flex-shrink:0; transition:all 0.15s; }
      .bear-opt-btn.selected .opt-check { background:var(--teal); border-color:var(--teal); color:white; }

      .bear-typing { display:flex; gap:4px; align-items:center; padding:4px 0; }
      .bear-typing-dot { width:6px; height:6px; background:var(--text-faint,#A0ABBE); border-radius:50%; animation:typeBounce 1.3s infinite ease-in-out; }
      .bear-typing-dot:nth-child(2){animation-delay:0.22s}
      .bear-typing-dot:nth-child(3){animation-delay:0.44s}
      @keyframes typeBounce{ 0%,80%,100%{transform:scale(0.4);opacity:0.4} 40%{transform:scale(1);opacity:1} }

      .bear-input-row { display:flex; gap:10px; padding:14px 18px; background:var(--surface); border:1px solid var(--border); border-top:none; border-radius:0 0 16px 16px; }
      .bear-text-input { flex:1; background:var(--surface-2,#F7F9FC); border:1.5px solid var(--border); border-radius:24px; padding:11px 18px; font-family:'DM Sans',sans-serif; font-size:14px; color:var(--text); outline:none; transition:border-color 0.2s; resize:none; min-height:44px; max-height:100px; line-height:1.5; }
      .bear-text-input:focus { border-color:var(--teal); box-shadow:0 0 0 3px rgba(11,184,169,0.1); }
      .bear-text-input::placeholder { color:var(--text-faint,#A0ABBE); }
      .bear-send-btn { width:44px; height:44px; background:var(--teal); border:none; border-radius:50%; color:white; font-size:18px; cursor:pointer; display:flex; align-items:center; justify-content:center; transition:all 0.2s; flex-shrink:0; }
      .bear-send-btn:hover { background:#089E90; transform:scale(1.05); }
      .bear-send-btn:disabled { opacity:0.4; cursor:not-allowed; transform:none; }

      .bear-no-report { text-align:center; padding:40px 24px; }
      .bear-no-report-icon { font-size:56px; margin-bottom:16px; }
      .bear-no-report h3 { font-family:'Plus Jakarta Sans',sans-serif; font-size:18px; font-weight:700; margin-bottom:8px; color:var(--text); }
      .bear-no-report p { font-size:14px; color:var(--text-muted); line-height:1.7; margin-bottom:20px; }
    </style>

    <div class="bear-chat-wrap">
      <!-- Header -->
      <div class="bear-chat-header">
        <div class="bear-chat-header-left">
          <div class="bear-avatar-lg">🐻</div>
          <div>
            <div class="bear-chat-name">Barita 🐾</div>
            <div class="bear-chat-sub">Your personal Wealth Advisor Bear · Barita Investments</div>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:12px">
          <div class="bear-online"><div class="bear-online-dot"></div>Online</div>
          ${profile ? `<span class="profile-badge ${profile.toLowerCase()}" style="font-size:11px">${esc(profile)}</span>` : ''}
        </div>
      </div>

      <!-- Messages -->
      <div class="bear-messages" id="bear-msgs">
        ${!hasReport ? `
          <div class="bear-no-report">
            <div class="bear-no-report-icon">🐻</div>
            <h3>Hi! I'm Barita 🎉</h3>
            <p>I haven't built your portfolio yet — complete the questionnaire first and I'll be able to give you personalised advice, explain your allocation, answer questions, and more!</p>
            <button class="btn-action" onclick="window.location.href='/questionnaire'">📋 Start Questionnaire →</button>
          </div>` : ''}
      </div>

      <!-- Input -->
      <div class="bear-input-row">
        <textarea class="bear-text-input" id="bear-input" placeholder="Ask me anything about your portfolio, investing, or strategy… 🍯" rows="1"></textarea>
        <button class="bear-send-btn" id="bear-send" ${!hasReport ? 'disabled' : ''}>→</button>
      </div>
    </div>
  `;

  // ── Init chat history ──
  if (hasReport && state.chatHistory.length === 0) {
    const bProfile = state.report?.behavioral_profile || state.report?.profile || 'Moderate';
    const conf     = state.report?.confidence?.score;
    const mc       = state.report?.monte_carlo;
    const greeting = `🐻 Hey ${esc(state.answers?.first_name || 'there')}! Pawsome to see you on the dashboard! 🎉

I've finished building your portfolio. You've been classified as a **${esc(bProfile)}** investor${conf ? ` with a confidence score of **${conf}/100**` : ''}. ${mc ? `Running the numbers through Monte Carlo simulation, there's a **${mc.prob_double}% chance** of doubling your initial investment over 10 years! 🍯` : ''}

Feel free to ask me anything — why I picked specific assets, what volatility means, how to read your report, or anything else on your mind!`;
    bearAddMessage(greeting, null, false);
  } else if (hasReport) {
    state.chatHistory.forEach(m => {
      if (m.role === 'advisor') bearAddMessage(m.text, null, false);
      else if (m.role === 'user') bearAddUserMessage(m.text, false);
    });
  }

  // ── Wire up input ──
  const inputEl = $('bear-input');
  const sendEl  = $('bear-send');
  if (!inputEl || !sendEl) return;

  inputEl.addEventListener('input', () => {
    sendEl.disabled = !inputEl.value.trim();
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 100) + 'px';
  });

  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); bearSend(); }
  });

  sendEl.addEventListener('click', bearSend);
}

// ── Bear message helpers ──────────────────────────────────────────────────────
function bearAddMessage(text, options, scroll = true) {
  const wrap = $('bear-msgs');
  if (!wrap) return;

  const row = document.createElement('div');
  row.className = 'bmsg-bear';
  row.innerHTML = `
    <div class="bmsg-bear-av">🐻</div>
    <div class="bmsg-bear-bubble">${bearFormat(text)}</div>
  `;
  wrap.appendChild(row);

  if (options && options.length) {
    const tray = document.createElement('div');
    tray.className = 'bear-options';
    tray.id = 'bear-options-tray';
    options.forEach(opt => {
      const btn = document.createElement('button');
      btn.className = 'bear-opt-btn';
      btn.innerHTML = `<span class="opt-check"></span>${esc(opt)}`;
      btn.addEventListener('click', () => {
        tray.querySelectorAll('.bear-opt-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        btn.querySelector('.opt-check').textContent = '✓';
        setTimeout(() => {
          tray.remove();
          bearSendText(opt);
        }, 280);
      });
      tray.appendChild(btn);
    });
    wrap.appendChild(tray);
  }

  if (scroll) bearScroll();
}

function bearAddUserMessage(text, scroll = true) {
  const wrap = $('bear-msgs');
  if (!wrap) return;
  const row = document.createElement('div');
  row.className = 'bmsg-user';
  row.innerHTML = `<div class="bmsg-user-bubble">${esc(text)}</div>`;
  wrap.appendChild(row);
  if (scroll) bearScroll();
}

function bearShowTyping() {
  const wrap = $('bear-msgs');
  if (!wrap) return;
  const row = document.createElement('div');
  row.className = 'bmsg-bear'; row.id = 'bear-typing';
  row.innerHTML = `<div class="bmsg-bear-av">🐻</div><div class="bmsg-bear-bubble"><div class="bear-typing"><div class="bear-typing-dot"></div><div class="bear-typing-dot"></div><div class="bear-typing-dot"></div></div></div>`;
  wrap.appendChild(row);
  bearScroll();
}

function bearRemoveTyping() {
  document.getElementById('bear-typing')?.remove();
}

function bearScroll() {
  const wrap = $('bear-msgs');
  if (wrap) setTimeout(() => wrap.scrollTop = wrap.scrollHeight, 50);
}

function bearFormat(text) {
  return esc(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>');
}

// ── Bear send ────────────────────────────────────────────────────────────────
async function bearSend() {
  const input = $('bear-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  input.style.height = 'auto';
  $('bear-send').disabled = true;
  bearSendText(text);
}

async function bearSendText(text) {
  if (!text.trim()) return;

  bearAddUserMessage(text);
  state.chatHistory.push({ role: 'user', text });

  // Clear any option trays
  document.getElementById('bear-options-tray')?.remove();

  bearShowTyping();

  try {
    const data = await callBackend('/chat', {
      message: text,
      answers: state.answers,
      report:  state.report,
      history: state.chatHistory.filter(m => !m.thinking).slice(-10),
    });
    bearRemoveTyping();
    const reply = data.reply || "Sorry, I had a little hiccup! 🐻 Try again?";
    bearAddMessage(reply, null);
    state.chatHistory.push({ role: 'advisor', text: reply });
  } catch(e) {
    bearRemoveTyping();
    bearAddMessage(`Oops! Something went wrong 🐾 (${e.message}). Make sure the backend is running!`, null);
  }

  const sendBtn = $('bear-send');
  if (sendBtn) sendBtn.disabled = false;
}

// Legacy stubs — kept so nothing crashes if called from elsewhere
function appendMessage(msg) { /* replaced by bear chat */ }
async function sendMessage() { await bearSend(); }

// ── REPORTS VIEW ──
async function renderReportsView(area) {
  area.innerHTML = `
    <div class="panel-header" style="padding:0 0 16px"><div class="panel-title">Your Reports</div></div>
    <div class="report-list" id="report-list">
      <div style="color:var(--text-faint);font-size:14px;padding:20px 0">Loading…</div>
    </div>
  `;

  const reports = await loadReportHistory();
  const list    = $('report-list');

  if (!reports.length && !state.report) {
    list.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📄</div>
        <div class="empty-h">No Reports Yet</div>
        <p class="empty-p">Complete the questionnaire to generate your first portfolio report.</p>
        <button class="btn-action" onclick="openQuestionnaire()">Start Questionnaire →</button>
      </div>`;
    return;
  }

  list.innerHTML = '';

  // Show current report first if exists
  if (state.report) {
    const item = el('div', 'report-item');
    item.innerHTML = `
      <div class="report-item-left">
        <h4>Portfolio Report — <span class="profile-badge ${state.report.profile.toLowerCase()}">${state.report.profile}</span></h4>
        <p>Current session · Click to download PDF</p>
      </div>
      <button class="btn-dl" id="dl-current">⬇ Download PDF</button>
    `;
    list.appendChild(item);
    item.querySelector('#dl-current').addEventListener('click', (e) => { e.stopPropagation(); downloadPDF('latest'); });
  }

  reports.forEach(r => {
    const date = r.createdAt?.toDate ? r.createdAt.toDate().toLocaleDateString('en-JM', { dateStyle: 'medium' }) : '—';
    const item = el('div', 'report-item');
    item.innerHTML = `
      <div class="report-item-left">
        <h4><span class="profile-badge ${r.profile?.toLowerCase()}">${r.profile}</span></h4>
        <p>${date}</p>
      </div>
      <button class="btn-dl">⬇ Download PDF</button>
    `;
    item.querySelector('.btn-dl').addEventListener('click', (e) => { e.stopPropagation(); downloadPDF(r.id); });
    list.appendChild(item);
  });
}

// ─── QUESTIONNAIRE ────────────────────────────────────────────────────────────
// Flatten sections into individual questions, respecting showIf
function getActiveQuestions() {
  const qs = [];
  SECTIONS.forEach(sec => {
    sec.questions.forEach(q => {
      if (!q.showIf || q.showIf(state.answers)) {
        qs.push({ ...q, sectionTitle: sec.title });
      }
    });
  });
  return qs;
}

// ─── TWO-PAGE QUESTIONNAIRE ──────────────────────────────────────────────────
// Page 1: Personal info (first_name, last_name, age) — shown together
// Page 2: All remaining questions — full scrollable page
// state.qPage tracks which page we're on (1 or 2)

window.openQuestionnaire = function() {
  window.location.href = '/questionnaire';
};

function closeQuestionnaire() { $('modal-questionnaire').classList.add('hidden'); }

function getProfileQuestions() {
  const profileSection = SECTIONS.find(s => s.id === 'profile');
  return profileSection ? profileSection.questions : [];
}

function getMainQuestions() {
  const qs = [];
  SECTIONS.forEach(sec => {
    if (sec.id === 'profile') return; // skip profile — shown on page 1
    sec.questions.forEach(q => {
      if (!q.showIf || q.showIf(state.answers)) {
        qs.push({ ...q, sectionTitle: sec.title });
      }
    });
  });
  return qs;
}

function renderQPage() {
  if (state.qPage === 1) renderPage1();
  else renderPage2();
}

// ── PAGE 1: Personal info (all 3 on one page) ──────────────────────────────
function renderPage1() {
  const profileQs = getProfileQuestions();
  const total = 2; // 2 pages total

  $('q-progress-fill').style.width = '0%';
  $('q-progress-pct').textContent  = '0%';
  $('q-btn-back').style.visibility = 'hidden';
  $('q-btn-next').textContent = 'Continue →';

  const body = $('q-body');
  body.innerHTML = `
    <div class="q-section-label">Page 1 of 2 · Your Profile</div>
    <div class="q-text" style="margin-bottom:6px">Let's start with a few details about you.</div>
    <div class="q-hint">This helps us personalise your portfolio report.</div>
    <div id="profile-fields" style="display:flex;flex-direction:column;gap:16px;margin-top:20px"></div>
  `;

  const fieldsWrap = $('profile-fields');
  profileQs.forEach(q => {
    const wrap = el('div', '');
    wrap.innerHTML = `
      <label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.04em">${esc(q.text)}</label>
      <input
        class="q-input"
        id="profile-input-${q.id}"
        type="${q.id === 'age' ? 'number' : 'text'}"
        placeholder="${esc(q.placeholder || '')}"
        value="${esc(state.answers[q.id] || '')}"
        min="${q.id === 'age' ? '16' : ''}"
        max="${q.id === 'age' ? '100' : ''}"
        style="width:100%"
      />
    `;
    fieldsWrap.appendChild(wrap);

    const input = wrap.querySelector(`#profile-input-${q.id}`);
    input.addEventListener('input', e => {
      state.answers[q.id] = e.target.value.trim();
      checkPage1Complete();
    });
  });

  checkPage1Complete();
}

function checkPage1Complete() {
  const profileQs = getProfileQuestions();
  const allFilled = profileQs.every(q => state.answers[q.id] && state.answers[q.id].toString().trim());
  $('q-btn-next').disabled = !allFilled;
}

// ── PAGE 2: Full scrollable questionnaire ─────────────────────────────────
function renderPage2() {
  const mainQs = getMainQuestions();

  $('q-progress-fill').style.width = '50%';
  $('q-progress-pct').textContent  = '50%';
  $('q-btn-back').style.visibility = 'visible';
  $('q-btn-next').textContent = 'Submit & Generate Portfolio ✓';
  $('q-btn-next').disabled = false;

  const body = $('q-body');
  body.innerHTML = `
    <div class="q-section-label">Page 2 of 2 · Investment Profile</div>
    <div class="q-text" style="margin-bottom:6px">Complete your investment profile below.</div>
    <div class="q-hint">Scroll through and answer all questions. Required questions are marked.</div>
    <div id="main-questions" style="margin-top:20px;display:flex;flex-direction:column;gap:28px"></div>
  `;

  const container = $('main-questions');
  let currentSection = '';

  mainQs.forEach((q, idx) => {
    // Section divider
    if (q.sectionTitle !== currentSection) {
      currentSection = q.sectionTitle;
      const divider = el('div', '');
      divider.innerHTML = `
        <div style="font-size:11px;font-weight:700;letter-spacing:0.10em;text-transform:uppercase;
                    color:var(--teal);padding:8px 0 4px;border-top:1px solid var(--border-light);
                    margin-top:4px">
          ${esc(currentSection)}
        </div>
      `;
      container.appendChild(divider);
    }

    const qWrap = el('div', '');
    qWrap.innerHTML = `
      <div style="font-size:15px;font-weight:600;color:var(--text);margin-bottom:${q.hint ? '4px' : '12px'};line-height:1.45">
        ${esc(q.text)}
      </div>
      ${q.hint ? `<div class="q-hint" style="margin-bottom:12px">${esc(q.hint)}</div>` : ''}
      <div id="q2-wrap-${q.id}"></div>
    `;
    container.appendChild(qWrap);

    const wrap = qWrap.querySelector(`#q2-wrap-${q.id}`);
    renderQuestionInput(q, wrap);
  });

  // Update progress on scroll
  const modal = document.querySelector('.modal-q');
  if (modal) {
    modal.addEventListener('scroll', updatePage2Progress);
  }
}

function updatePage2Progress() {
  const modal = document.querySelector('.modal-q');
  if (!modal) return;
  const scrolled = modal.scrollTop / (modal.scrollHeight - modal.clientHeight);
  const pct = Math.round(50 + scrolled * 50);
  $('q-progress-fill').style.width = pct + '%';
  $('q-progress-pct').textContent  = pct + '%';
}

function renderQuestionInput(q, wrap) {
  if (q.type === 'single') {
    const opts = el('div', 'q-options');
    q.options.forEach(opt => {
      const btn = el('button', `q-opt${state.answers[q.id] === opt ? ' selected' : ''}`);
      btn.textContent = opt;
      btn.addEventListener('click', () => {
        state.answers[q.id] = opt;
        opts.querySelectorAll('.q-opt').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
      });
      opts.appendChild(btn);
    });
    wrap.appendChild(opts);

  } else if (q.type === 'multi') {
    const selected = state.answers[q.id] || [];
    const opts = el('div', 'q-options');
    q.options.forEach(opt => {
      const btn = el('button', `q-opt${selected.includes(opt) ? ' selected' : ''}`);
      btn.textContent = opt;
      btn.addEventListener('click', () => {
        const cur = state.answers[q.id] || [];
        if (cur.includes(opt)) { state.answers[q.id] = cur.filter(x => x !== opt); btn.classList.remove('selected'); }
        else                   { state.answers[q.id] = [...cur, opt];              btn.classList.add('selected'); }
      });
      opts.appendChild(btn);
    });
    wrap.appendChild(opts);

  } else if (q.type === 'text') {
    const input = el('input', 'q-input');
    input.type        = 'text';
    input.placeholder = q.placeholder || '';
    input.value       = state.answers[q.id] || '';
    input.style.width = '100%';
    input.addEventListener('input', e => { state.answers[q.id] = e.target.value; });
    wrap.appendChild(input);

  } else if (q.type === 'textarea') {
    const ta = el('textarea', 'q-input q-textarea');
    ta.placeholder = q.placeholder || '';
    ta.value       = state.answers[q.id] || '';
    ta.style.width = '100%';
    ta.addEventListener('input', e => { state.answers[q.id] = e.target.value; });
    wrap.appendChild(ta);
  }
}

function isAnswered(q) {
  if (q.type === 'multi' || q.type === 'textarea') return true;
  return !!state.answers[q.id];
}

async function advanceQuestion() {
  if (state.qPage === 1) {
    state.qPage = 2;
    renderQPage();
  } else {
    closeQuestionnaire();
    await submitQuestionnaire();
  }
}

async function submitQuestionnaire() {
  // Show loading on portfolio view
  switchView('portfolio');
  $('view-area').innerHTML = `
    <div class="panel">
      <div class="empty-state">
        <div class="empty-icon">⚙️</div>
        <div class="empty-h">Building Your Portfolio…</div>
        <p class="empty-p">Our AI is analysing your profile and generating your personalised allocation.</p>
        <div class="thinking" style="justify-content:center;margin-top:12px"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>
      </div>
    </div>`;

  try {
    const data = await callBackend('/analyse', { answers: state.answers });
    state.report = data;

    // Save to Firestore
    await saveSession();
    await addDoc(collection(db, 'users', state.user.uid, 'reports'), {
      profile:      data.profile,
      profile_label:data.profile_label,
      metrics:      data.metrics,
      allocations:  data.allocations,
      answers:      state.answers,
      createdAt:    serverTimestamp(),
    });

    renderView('portfolio');
  } catch(e) {
    $('view-area').innerHTML = `
      <div class="panel">
        <div class="empty-state">
          <div class="empty-icon">⚠️</div>
          <div class="empty-h">Analysis Failed</div>
          <p class="empty-p">Could not connect to the backend: ${esc(e.message)}<br/><br/>Make sure your Flask server is running and BACKEND_URL is correct in app.js.</p>
          <button class="btn-action" onclick="switchView('questionnaire')">← Back</button>
        </div>
      </div>`;
  }
}

// ─── POST-LOAD MINI ALLOC ─────────────────────────────────────────────────────
function maybeRenderMiniAlloc() {
  const el2 = $('mini-alloc');
  if (!el2 || !state.report?.allocations) return;
  state.report.allocations.slice(0,6).forEach(a => {
    const row = el('div', 'alloc-row-item');
    row.innerHTML = `
      <div class="alloc-dot" style="background:${a.color||'#0BB8A9'}"></div>
      <div style="flex:1"><div class="alloc-name" style="font-size:12px">${esc(a.label)}</div></div>
      <div class="alloc-bar-outer"><div class="alloc-bar-inner" style="background:${a.color||'#0BB8A9'}" data-pct="${a.pct}"></div></div>
      <div class="alloc-pct">${a.pct}%</div>
    `;
    el2.appendChild(row);
  });
  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.querySelectorAll('.alloc-bar-inner').forEach(b => { b.style.width = b.dataset.pct + '%'; });
  }));
}

// ─── BIND EVENTS ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  $('btn-google').addEventListener('click', handleGoogleSignIn);
  $('btn-email-auth').addEventListener('click', handleEmailAuth);
  $('btn-forgot').addEventListener('click', async () => {
    const email = $('input-email').value.trim();
    if (!email) { setLoginError('Enter your email above first.'); return; }
    try { await sendPasswordResetEmail(auth, email); alert('Password reset email sent.'); }
    catch(e) { setLoginError('Could not send reset email: ' + e.message); }
  });
  $('btn-toggle-mode').addEventListener('click', toggleRegisterMode);
  $('btn-close-q').addEventListener('click', closeQuestionnaire);
  $('q-btn-next').addEventListener('click', advanceQuestion);
  $('q-btn-back').addEventListener('click', () => { if (state.qPage === 2) { state.qPage = 1; renderQPage(); } });

  ['input-email','input-password'].forEach(id => {
    $(id)?.addEventListener('keydown', e => { if (e.key === 'Enter') handleEmailAuth(); });
  });
});

// expose globals for inline onclick
window.switchView      = switchView;
window.openQuestionnaire = window.openQuestionnaire;