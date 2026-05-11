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

const BACKEND_URL = window.location.origin;

// ─── FIREBASE IMPORTS ─────────────────────────────────────────────────────────
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";

import {
  getAuth,
  onAuthStateChanged,
  signOut,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  updateProfile,
  sendPasswordResetEmail
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

import {
  getFirestore,
  doc,
  setDoc,
  getDoc,
  collection,
  addDoc,
  query,
  orderBy,
  limit,
  getDocs,
  serverTimestamp
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js";

const app = initializeApp(FIREBASE_CONFIG);
const auth = getAuth(app);
const db = getFirestore(app);

// ─── STATE ────────────────────────────────────────────────────────────────────
const state = {
  user: null,
  firebaseToken: null,
  answers: {},
  qStep: 0,
  qPage: 1,
  report: null,
  chatHistory: [],
  currentView: "dashboard",
  isRegister: false
};

// ─── QUESTIONNAIRE DEFINITION ─────────────────────────────────────────────────
const SECTIONS = [
  {
    id: "profile",
    title: "Your Profile",
    questions: [
      { id: "first_name", text: "First Name", type: "text", placeholder: "e.g. Jane" },
      { id: "last_name", text: "Last Name", type: "text", placeholder: "e.g. Smith" },
      { id: "age", text: "Age", type: "text", placeholder: "e.g. 28" }
    ]
  },
  {
    id: "background",
    title: "Your Background",
    questions: [
      {
        id: "knowledge_level",
        text: "How much do you know about investing?",
        type: "single",
        options: [
          "I'm completely new to investing",
          "I have basic knowledge but no real experience",
          "I've been learning and have some experience",
          "I have a lot of investing experience"
        ]
      },
      {
        id: "employment_status",
        text: "What is your employment status?",
        type: "single",
        options: [
          "Salaried employee",
          "Self-employed / business owner",
          "Part-time / contract",
          "Unemployed",
          "Retired"
        ]
      },
      {
        id: "pay_frequency",
        text: "How often do you get paid?",
        type: "single",
        options: [
          "Monthly",
          "Weekly",
          "Commission-based",
          "Self-employed (irregular)"
        ]
      }
    ]
  },
  {
    id: "dependents",
    title: "Financial Dependents",
    questions: [
      {
        id: "dependents",
        text: "Do you have financial dependents?",
        type: "single",
        options: [
          "None",
          "1-2 children",
          "3+ children",
          "Elderly parents",
          "Children + parents",
          "Other dependents"
        ]
      }
    ]
  },
  {
    id: "existing_investments",
    title: "Existing Investments",
    questions: [
      {
        id: "other_investments",
        text: "Do you hold investments or pensions elsewhere?",
        type: "multi",
        hint: "Select all that apply",
        options: [
          "No other investments",
          "Local stocks / bonds",
          "Pension / NIS",
          "Foreign investments",
          "Real estate"
        ]
      }
    ]
  },
  {
    id: "tax",
    title: "Tax Residency",
    questions: [
      {
        id: "tax_residency",
        text: "In which country are you a tax resident?",
        type: "multi",
        hint: "Select all that apply",
        options: [
          "Jamaica only",
          "USA",
          "UK",
          "Canada",
          "Other"
        ]
      }
    ]
  },
  {
    id: "goals",
    title: "Financial Goals",
    questions: [
      {
        id: "primary_goal",
        text: "What is your primary financial goal?",
        type: "single",
        options: [
          "Wealth accumulation / growth",
          "Retirement planning",
          "Education funding",
          "Property purchase",
          "Income generation",
          "Capital preservation",
          "Emergency fund building"
        ]
      },
      {
        id: "goal_priority",
        text: "How would you describe the priority of this goal?",
        type: "single",
        options: [
          "Essential - I must achieve this",
          "Aspirational - I would like to achieve this"
        ]
      },
      {
        id: "withdrawal_time",
        text: "Over the next 2 years, how much do you expect to withdraw from this portfolio?",
        type: "single",
        options: [
          "No withdrawals",
          "Less than 10%",
          "10-25%",
          "More than 25%"
        ]
      }
    ]
  },
  {
    id: "risk_reaction",
    title: "Risk Reaction",
    questions: [
      {
        id: "drop_reaction",
        text: "How would you react if your investment dropped by 20%?",
        type: "single",
        options: [
          "Sell everything to avoid further losses",
          "Sell some to reduce losses",
          "Wait for recovery",
          "Invest more at lower prices"
        ]
      }
    ]
  },
  {
    id: "risk_profile",
    title: "Risk Profile",
    questions: [
      {
        id: "risk_relationship",
        text: "Which best describes your relationship with investment risk?",
        type: "single",
        options: [
          "I'm okay with small changes, but big losses stress me",
          "I understand ups and downs and stay calm",
          "I'm comfortable with big risks and see drops as opportunities",
          "I worry a lot about losing money"
        ]
      },
      {
        id: "loss_vs_gain",
        text: "Which outcome would upset you more?",
        type: "single",
        options: [
          "Missing a 20% gain",
          "Suffering a 20% loss"
        ]
      },
      {
        id: "performance_benchmark",
        text: "When reviewing your portfolio, what do you mainly compare it to?",
        type: "single",
        options: [
          "The amount I originally invested",
          "The overall increase in value (JMD gains)",
          "My expected return",
          "A market index",
          "The rate of inflation"
        ]
      },
      {
        id: "max_loss",
        text: "What is the maximum annual loss you could tolerate without changing strategy?",
        type: "single",
        options: [
          "Up to 10%",
          "Up to 20%",
          "Up to 40%",
          "More than 40%"
        ]
      }
    ]
  },
  {
    id: "resilience",
    title: "Financial Resilience",
    questions: [
      {
        id: "income_loss_runway",
        text: "If you lost your primary income, how long could you maintain your lifestyle without touching investments?",
        type: "single",
        options: [
          "Less than 3 months",
          "3-6 months",
          "6-12 months",
          "1-2 years",
          "More than 2 years"
        ]
      },
      {
        id: "debt_situation",
        text: "What best describes your current debt situation?",
        type: "single",
        options: [
          "Debt-free",
          "Minor debt",
          "Moderate debt",
          "Significant debt"
        ]
      }
    ]
  },
  {
    id: "currency",
    title: "Currency Profile",
    questions: [
      {
        id: "earn_currency",
        text: "In what currency do you primarily earn?",
        type: "single",
        options: [
          "JMD only",
          "USD only",
          "Mostly JMD",
          "Mostly USD",
          "Equal amounts of JMD and USD"
        ]
      },
      {
        id: "spend_currency",
        text: "In what currency do you primarily spend?",
        type: "single",
        options: [
          "JMD only",
          "USD only",
          "Mostly JMD",
          "Mostly USD",
          "Equal amounts of JMD and USD"
        ]
      },
      {
        id: "usd_liabilities",
        text: "Do you have USD-denominated liabilities?",
        type: "single",
        options: [
          "None",
          "Under USD $10K",
          "USD $10K-$50K",
          "USD $50K-$200K",
          "Over USD $200K"
        ]
      },
      {
        id: "inflation_impact",
        text: "How much does JMD inflation affect your cost of living?",
        type: "single",
        options: [
          "Not sure",
          "Minimal",
          "Moderate",
          "Significant",
          "Severe"
        ]
      }
    ]
  },
  {
    id: "management",
    title: "Portfolio Management",
    questions: [
      {
        id: "review_frequency",
        text: "How often should your portfolio be reviewed and rebalanced?",
        type: "single",
        options: [
          "Monthly",
          "Quarterly",
          "Semi-annually",
          "Annually",
          "Only when needed"
        ]
      },
      {
        id: "market_adjustment",
        text: "Are you open to adjusting your portfolio based on market conditions?",
        type: "single",
        options: [
          "No - keep it fixed",
          "Yes - small changes",
          "Yes - moderate changes",
          "Yes - fully active"
        ]
      },
      {
        id: "inflation_protection",
        text: "Do you want inflation protection in your portfolio?",
        type: "single",
        options: [
          "Yes - strong focus",
          "Somewhat",
          "Not necessary",
          "Not sure"
        ]
      },
      {
        id: "invest_style",
        text: "What is your preferred investment style?",
        type: "single",
        options: [
          "Fully passive",
          "Mostly passive",
          "Balanced",
          "Mostly active",
          "Fully active"
        ]
      },
      {
        id: "involvement_level",
        text: "How involved do you want to be in decisions?",
        type: "single",
        options: [
          "Hands-off",
          "Consulted on major changes",
          "Approve major decisions",
          "Fully involved"
        ]
      }
    ]
  }
];

// ─── QUESTION FLOW ──────────────────────────────────────────────────────────────
const QUESTION_FLOW = [
  { field: "first_name", question: "What's your first name? I like to keep things personal! 🍯", options: null },
  { field: "last_name", question: "And your last name?", options: null },
  { field: "age", question: "How old are you? Just the number is fine!", options: null },
  { field: "knowledge_level", question: "How would you describe your investing experience?", options: ["I'm completely new to investing", "I have basic knowledge but no real experience", "I've been learning and have some experience", "I have a lot of investing experience"] },
  { field: "primary_goal", question: "What's your #1 financial goal right now?", options: ["Wealth accumulation / growth", "Retirement planning", "Education funding", "Property purchase", "Income generation", "Capital preservation", "Emergency fund building"] },
  { field: "time_horizon", question: "How many years before you'd need to access this money? A rough estimate is perfect.", options: null },
  { field: "target_amount", question: "Do you have a specific money target in mind? For example, 'double my money', 'JMD 5 million', or 'not sure'.", options: null },
  { field: "withdrawal_time", question: "Over the next 2 years, how much of this portfolio might you need to withdraw?", options: ["No withdrawals", "Less than 10%", "10-25%", "More than 25%"] },
  { field: "drop_reaction", question: "If your portfolio dropped 20% in one month, what would you honestly do? 😬", options: ["Sell everything to avoid further losses", "Sell some to reduce losses", "Wait for recovery", "Invest more at lower prices"] },
  { field: "risk_comfort", question: "On a scale of 1–10, how much annual drawdown could you stomach before reconsidering your strategy? 1 means very little, 10 means big swings are okay.", options: null },
  { field: "max_loss", question: "What's the maximum annual loss you could handle without changing your plan?", options: ["Up to 10%", "Up to 20%", "Up to 40%", "More than 40%"] },
  { field: "sector_view", question: "Do you have a strong view that any sector will outperform? You can say something like 'tech', 'local JMD assets', or 'not sure'.", options: null },
  { field: "income_loss_runway", question: "If you lost your income tomorrow, how long could you live comfortably without touching investments?", options: ["Less than 3 months", "3-6 months", "6-12 months", "1-2 years", "More than 2 years"] },
  { field: "debt_situation", question: "How would you describe your current debt situation?", options: ["Debt-free", "Minor debt", "Moderate debt", "Significant debt"] },
  { field: "earn_currency", question: "What currency do you mainly earn in?", options: ["JMD only", "USD only", "Mostly JMD", "Mostly USD", "Equal amounts of JMD and USD"] },
  { field: "spend_currency", question: "What currency do you mainly spend in?", options: ["JMD only", "USD only", "Mostly JMD", "Mostly USD", "Equal amounts of JMD and USD"] },
  { field: "usd_liabilities", question: "Do you have any USD-denominated debts or liabilities?", options: ["None", "Under USD $10K", "USD $10K-$50K", "USD $50K-$200K", "Over USD $200K"] },
  { field: "inflation_impact", question: "How much does JMD inflation affect your daily costs?", options: ["Not sure", "Minimal", "Moderate", "Significant", "Severe"] },
  { field: "inflation_protection", question: "Do you want inflation protection built into your portfolio?", options: ["Not sure", "Not necessary", "Somewhat", "Yes - strong focus"] },
  { field: "invest_style", question: "What's your preferred investing style?", options: ["Fully passive", "Mostly passive", "Balanced", "Mostly active", "Fully active"] },
  { field: "market_adjustment", question: "If market conditions shifted, would you be open to adjusting your portfolio?", options: ["No - keep it fixed", "Yes - small changes", "Yes - moderate changes", "Yes - fully active"] },
  { field: "risk_relationship", question: "Which best describes your relationship with investment risk?", options: ["I worry a lot about losing money", "I'm okay with small changes, but big losses stress me", "I understand ups and downs and stay calm", "I'm comfortable with big risks and see drops as opportunities"] },
  { field: "loss_vs_gain", question: "Which outcome would upset you more?", options: ["Missing a 20% gain", "Suffering a 20% loss"] },
  { field: "performance_benchmark", question: "When checking your portfolio, what do you mainly compare it against?", options: ["The amount I originally invested", "The overall increase in value (JMD gains)", "My expected return", "A market index", "The rate of inflation"] }
];

// ─── HELPERS ──────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const el = (tag, cls = "", html = "") => {
  const e = document.createElement(tag);

  if (cls) {
    e.className = cls;
  }

  if (html) {
    e.innerHTML = html;
  }

  return e;
};

const esc = s => String(s ?? "")
  .replace(/&/g, "&amp;")
  .replace(/</g, "&lt;")
  .replace(/>/g, "&gt;");

  
function switchView(view) {
  state.currentView = view;

  document
    .querySelectorAll(".nav-item")
    .forEach(b => b.classList.toggle("active", b.dataset.view === view));

  const titles = {
    dashboard: "Dashboard",
    portfolio: "My Portfolio",
    advisor: "🐻 AI Chatbot",
    reports: "Reports",
    profile: "Profile"
  };

  $("topbar-title").textContent = titles[view] || view;

  renderView(view);

  setTimeout(maybeRenderMiniAlloc, 0);
}

// ─── SESSION STORAGE HELPERS ─────────────────────────────────────────────────
function getUserStorageKeys() {

  const uid = state.user?.uid || "guest";

  return {
    report: `barita_report_${uid}`,
    answers: `barita_answers_${uid}`,
    chatHistory: `barita_chat_history_${uid}`
  };
}

function saveLocalSession() {

  if (!state.user) return;

  const keys = getUserStorageKeys();

  if (state.report) {
    sessionStorage.setItem(
      keys.report,
      JSON.stringify(state.report)
    );
  }

  if (state.answers) {
    sessionStorage.setItem(
      keys.answers,
      JSON.stringify(state.answers)
    );
  }

  if (state.chatHistory) {
    sessionStorage.setItem(
      keys.chatHistory,
      JSON.stringify(state.chatHistory)
    );
  }
}

function loadLocalSession() {

  if (!state.user) return;

  const keys = getUserStorageKeys();

  const savedReport = sessionStorage.getItem(keys.report);
  const savedAnswers = sessionStorage.getItem(keys.answers);
  const savedChat = sessionStorage.getItem(keys.chatHistory);

  if (savedReport) {
    state.report = JSON.parse(savedReport);
  }

  if (savedAnswers) {
    state.answers = JSON.parse(savedAnswers);
  }

  if (savedChat) {
    state.chatHistory = JSON.parse(savedChat);
  }
}

// ─── FIRESTORE SESSION LOADING ───────────────────────────────────────────────
async function loadSession() {

  loadLocalSession();

  try {

    if (!state.user || !db) return;

    const docRef = doc(
      db,
      "sessions",
      state.user.uid
    );

    const docSnap = await getDoc(docRef);

    if (docSnap.exists()) {

      const data = docSnap.data();

      if (data.report) {
        state.report = data.report;
      }

      if (data.answers) {
        state.answers = data.answers;
      }

      if (data.chatHistory) {
        state.chatHistory = data.chatHistory;
      }
    }

  } catch (err) {

    console.warn(
      "Firestore session load skipped:",
      err.message
    );
  }
}

// ─── SAVE SESSION ────────────────────────────────────────────────────────────
async function saveSession() {

  try {

    saveLocalSession();

    if (!state.user || !db) return;

    await setDoc(
      doc(db, "sessions", state.user.uid),
      {
        report: state.report || null,
        answers: state.answers || {},
        chatHistory: state.chatHistory || [],
        updatedAt: serverTimestamp()
      },
      { merge: true }
    );

  } catch (err) {

    console.warn(
      "Firestore save failed:",
      err.message
    );
  }
}

// ─── AUTH STATE ──────────────────────────────────────────────────────────────
onAuthStateChanged(auth, async user => {
  if (user) {
    state.user = user;
    state.firebaseToken = await user.getIdToken();

    setInterval(async () => {
      state.firebaseToken = await user.getIdToken(true);
    }, 50 * 60 * 1000);

    document.getElementById("screen-login").classList.add("hidden");
    document.getElementById("screen-app").classList.remove("hidden");

    const name = user.displayName || user.email.split("@")[0];
    const initial = name[0].toUpperCase();

    document.getElementById("sidebar-name").textContent = name;
    document.getElementById("sidebar-email").textContent = user.email;
    document.getElementById("sidebar-avatar").textContent = initial;
    document.getElementById("topbar-avatar").textContent = initial;

    document.getElementById("sidebar-email")?.addEventListener("click", () => {
  switchView("profile");
});

    document.getElementById("sidebar-name")?.addEventListener("click", () => {
      switchView("profile");
    });

    document.getElementById("topbar-avatar")?.addEventListener("click", () => {
      switchView("profile");
    });

    await loadSession();

    switchView("dashboard");
  } else {
    state.user = null;

    document.getElementById("screen-app").classList.add("hidden");
    document.getElementById("screen-login").classList.remove("hidden");
  }
});

// ─── GOOGLE LOGIN ────────────────────────────────────────────────────────────
window.googleLogin = async () => {

  try {

    const provider = new GoogleAuthProvider();

    await signInWithPopup(auth, provider);

  } catch (err) {

    alert(err.message);
  }
};

// ─── EMAIL LOGIN ─────────────────────────────────────────────────────────────
window.emailAuth = async () => {

  const email = $("email").value.trim();
  const password = $("password").value.trim();

  if (!email || !password) {
    return alert("Please fill in all fields.");
  }

  try {

    if (state.isRegister) {
      const confirmPassword = $("confirm-password")?.value.trim();

      if (password !== confirmPassword) {
      return alert("Passwords do not match.");
      }
      const cred =
        await createUserWithEmailAndPassword(
          auth,
          email,
          password
        );

      const name = $("full-name")?.value.trim() || "";

      if (name) {
        await updateProfile(cred.user, {
          displayName: name
        });
      }

    } else {

      await signInWithEmailAndPassword(
        auth,
        email,
        password
      );
    }

  } catch (err) {

    alert(err.message);
  }
};

// ─── TOGGLE REGISTER ─────────────────────────────────────────────────────────
window.toggleRegister = () => {
  state.isRegister = !state.isRegister;

  $("register-fields").classList.toggle("hidden", !state.isRegister);
  $("register-confirm").classList.toggle("hidden", !state.isRegister);

  $("auth-title").textContent =
    state.isRegister ? "Create your account" : "Sign in to your account";

  $("auth-sub").textContent =
    state.isRegister
      ? "Join the Barita SOC 2026 platform."
      : "Welcome back. Enter your details below.";

  $("toggle-label").textContent =
    state.isRegister ? "Already have an account?" : "Don't have an account?";

  $("btn-toggle-mode").textContent =
    state.isRegister ? "Sign in instead" : "Create one";

  $("btn-email-text").textContent =
    state.isRegister ? "Create Account" : "Sign In";
};

// ─── PASSWORD RESET ──────────────────────────────────────────────────────────
window.resetPassword = async () => {

  const email = $("email").value.trim();

  if (!email) {
    return alert("Enter your email first.");
  }

  try {

    await sendPasswordResetEmail(auth, email);

    alert(
      "Password reset email sent."
    );

  } catch (err) {

    alert(err.message);
  }
};

// ─── SIGN OUT ────────────────────────────────────────────────────────────────
window.handleSignOut = async () => {

  const keys = getUserStorageKeys();

  sessionStorage.removeItem(keys.report);
  sessionStorage.removeItem(keys.answers);
  sessionStorage.removeItem(keys.chatHistory);

  localStorage.removeItem(keys.report);
  localStorage.removeItem(keys.answers);
  localStorage.removeItem(keys.chatHistory);

  sessionStorage.removeItem("barita_report");
  sessionStorage.removeItem("barita_answers");

  localStorage.removeItem("barita_report");
  localStorage.removeItem("barita_answers");

  state.answers = {};
  state.report = null;
  state.chatHistory = [];
  state.qStep = 0;

  await signOut(auth);
};

// ─── RENDER MAIN VIEWS ───────────────────────────────────────────────────────
function renderView(view) {
  const mount = document.getElementById("view-area");

  if (!mount) return;

  mount.innerHTML = "";

  if (view === "dashboard") {
    renderDashboard(mount);
    setTimeout(drawDashboardCharts, 0);
  } else if (view === "portfolio") {
    renderPortfolio(mount);
  } else if (view === "advisor") {
    renderAdvisor(mount);
  } else if (view === "reports") {
    renderReports(mount);
  } else if (view === "profile") {
  renderProfile(mount);
}}

// ─── BACKEND CALLS ───────────────────────────────────────────────────────────
async function callBackend(endpoint, payload = {}) {

  const token =
    state.firebaseToken ||
    await state.user.getIdToken();

  const res = await fetch(
    `${BACKEND_URL}${endpoint}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify(payload)
    }
  );

  if (!res.ok) {
    throw new Error(
      await res.text()
    );
  }

  return await res.json();
}


// ─── DASHBOARD ───────────────────────────────────────────────────────────────
function renderDashboard(mount) {

  const hasReport =
    !!state.report?.allocations?.length;

  const name =
    state.user?.displayName?.split(" ")[0] ||
    "there";

  const profile =
    state.report?.behavioral_profile ||
    state.report?.profile ||
    "—";

  const metrics =
    state.report?.metrics || {};

  const mc = getMonteCarlo();

  mount.innerHTML = `
      <section class="hero-card">

        <div class="hero-text">
          <h1>
            Welcome back, ${esc(name)} 👋
          </h1>

          <p>
            ${
              hasReport
                ? `Your <strong>${esc(profile)}</strong> portfolio is live and actively optimised using Monte Carlo simulation, MVO, HRP and diversification analytics.`
                : `Start building your AI-powered investment portfolio with Barita Bear.`
            }
          </p>

          <button
            class="hero-btn"
            onclick="switchView('${hasReport ? "portfolio" : "advisor"}')"
          >
            ${hasReport ? "📊 Open Portfolio" : "🐻 Start AI Chatbot"}
          </button>
        </div>

        <img
          src="images/barita-bear.png"
          class="hero-bear"
        />

      </section>

      <section class="stat-grid">

        <div class="stat-card">
          <div class="stat-card-label">
            📈 Expected Return
          </div>

          <div class="stat-card-val" style="color:var(--green)">
            ${metrics.expected_return || "—"}
          </div>

          <div class="stat-card-sub">
            Annualised estimate
          </div>
        </div>

        <div class="stat-card">
          <div class="stat-card-label">
            🎯 Risk Profile
          </div>

          <div class="stat-card-val" style="font-size:18px">
            ${
              hasReport
                ? `<span class="profile-badge ${String(profile).toLowerCase()}">${esc(profile)}</span>`
                : "—"
            }
          </div>

          <div class="stat-card-sub">
            ${esc(state.report?.confidence?.label || "Not yet assessed")}
          </div>
        </div>

        <div class="stat-card">
          <div class="stat-card-label">
            🎲 Goal Probability
          </div>

          <div class="stat-card-val" style="color:var(--teal)">
            ${
              mc.prob_goal !== undefined
                ? mc.prob_goal + "%"
                : "—"
            }
          </div>

          <div class="stat-card-sub">
            Monte Carlo simulation
          </div>
        </div>

        <div class="stat-card">
          <div class="stat-card-label">
            ⚡ Sharpe Ratio
          </div>

          <div class="stat-card-val" style="color:#8B5CF6">
            ${metrics.sharpe_ratio || "—"}
          </div>

          <div class="stat-card-sub">
            Risk-adjusted return
          </div>
        </div>

      </section>

      <section class="dashboard-two-col">

        <div class="chart-card">
          <div class="panel-header">
            <div>
              <div class="panel-title">
                📊 Portfolio Allocation
              </div>

              <div class="panel-sub">
                Where your money is going
              </div>
            </div>
          </div>

          <div
            style="
              height:320px;
              position:relative;
              margin-top:20px;
            "
          >
            <canvas id="dashboard-donut"></canvas>
          </div>
        </div>

        <div class="chart-card">

          <div class="panel-header">
            <div>
              <div class="panel-title">
                📌 Market Snapshot
              </div>

              <div class="panel-sub">
                Portfolio health indicators
              </div>
            </div>
          </div>

          <div style="margin-top:10px">

            <div class="market-item">
              <span>Portfolio Volatility</span>
              <span class="market-red">
                ${metrics.volatility || "—"}
              </span>
            </div>

            <div class="market-item">
              <span>Expected Return</span>
              <span class="market-green">
                ${metrics.expected_return || "—"}
              </span>
            </div>

            <div class="market-item">
              <span>Goal Achievement</span>
              <span class="market-green">
                ${
                  mc.prob_goal !== undefined
                    ? mc.prob_goal + "%"
                    : "—"
                }
              </span>
            </div>

            <div class="market-item">
              <span>Risk Strategy</span>
              <span>
                ${esc(profile)}
              </span>
            </div>

          </div>

          <div class="insight-banner">
            <div style="font-size:48px">
              🐻
            </div>

            <div>
              <div style="font-weight:800;font-size:16px;margin-bottom:6px">
                Barita Bear Insight
              </div>

              <div style="font-size:13px;line-height:1.7;color:rgba(255,255,255,.82)">
                ${
                  profile === "Conservative"
                    ? "Your portfolio prioritises stability and downside protection."
                    : profile === "Aggressive"
                    ? "Your allocation focuses on long-term capital growth."
                    : "Your portfolio balances growth potential with risk control."
                }
              </div>
            </div>
          </div>

        </div>

      </section>

      ${
        hasReport
          ? renderDashboardPortfolioPreview()
          : `
            <section class="panel">
              <div class="empty-state">
                <div class="empty-icon">🐻</div>

                <div class="empty-h">
                  Start Your AI Profiling Chat
                </div>

                <p class="empty-p">
                  Barita Bear will build your personalised investment portfolio step-by-step.
                </p>

                <button
                  class="btn-action"
                  onclick="switchView('advisor')"
                >
                  Start AI Chatbot →
                </button>
              </div>
            </section>
          `
      }
    `;
}

function drawDashboardCharts() {
  const donut = document.getElementById("dashboard-donut");

  if (!donut || typeof Chart === "undefined") {
    return;
  }

  const allocations = state.report?.allocations || [];

  if (!allocations.length) {
    return;
  }

  new Chart(donut.getContext("2d"), {
    type: "doughnut",
    data: {
      labels: allocations.map(a => a.label || a.ticker),
      datasets: [
        {
          data: allocations.map(a => Number(a.pct || 0)),
          backgroundColor: allocations.map(a => a.color || "#0BB8A9"),
          borderWidth: 0,
          hoverOffset: 8
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "68%",
      plugins: {
        legend: {
          position: "right"
        }
      }
    }
  });
}


function renderDashboardPortfolioPreview() {

  const allocations =
    state.report?.allocations || [];

  const metrics =
    state.report?.metrics || {};

  const method =
    metrics.optimization_method ||
    metrics.mvo_strategy ||
    state.report?.mvo_strategy ||
    "Optimised";

  const mc = getMonteCarlo();

  const topRows = allocations
    .slice(0, 7)
    .map(asset => `
      <div class="alloc-row-item">
        <div
          class="alloc-dot"
          style="background:${asset.color || "#0BB8A9"}"
        ></div>

        <div style="flex:1;min-width:0">
          <div class="alloc-name">
            ${esc(asset.label || asset.ticker || "Asset")}
          </div>

          <div class="alloc-ticker">
            ${esc(asset.ticker || "")} · ${esc(asset.class || "Asset")}
          </div>
        </div>

        <div class="alloc-bar-outer">
          <div
            class="alloc-bar-inner"
            style="width:${Number(asset.pct || 0)}%;background:${asset.color || "#0BB8A9"}"
          ></div>
        </div>

        <div class="alloc-pct">
          ${pctFmt(asset.pct)}
        </div>
      </div>
    `)
    .join("");

  return `
    <section class="three-col">
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">
              Where Your Money Is Going
            </div>
            <div class="panel-sub">
              Real allocation returned from /analyse
            </div>
          </div>

          <button class="btn-dl" onclick="switchView('portfolio')">
            View full →
          </button>
        </div>

        <div class="panel-body">
          <div class="alloc-table">
            ${topRows}
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">
              Optimisation Summary
            </div>
            <div class="panel-sub">
              ${esc(method)}
            </div>
          </div>
        </div>

        <div class="panel-body">
          <div style="display:flex;flex-direction:column;gap:14px">
            <div>
              <div class="stat-card-label">
                Expected Return
              </div>
              <div style="font-family:var(--font-display);font-size:22px;font-weight:700;color:var(--green)">
                ${metrics.expected_return || "—"}
              </div>
            </div>

            <div class="divider"></div>

            <div>
              <div class="stat-card-label">
                Volatility
              </div>
              <div style="font-family:var(--font-display);font-size:22px;font-weight:700;color:var(--red)">
                ${metrics.volatility || "—"}
              </div>
            </div>

            <div class="divider"></div>

            <div>
              <div class="stat-card-label">
                Sharpe Ratio
              </div>
              <div style="font-family:var(--font-display);font-size:22px;font-weight:700;color:var(--teal)">
                ${metrics.sharpe_ratio || "—"}
              </div>
            </div>

            <div class="divider"></div>

            <div>
              <div class="stat-card-label">
                Monte Carlo Goal Probability
              </div>
              <div style="font-family:var(--font-display);font-size:22px;font-weight:700;color:var(--teal)">
                ${
                  mc.prob_goal !== undefined
                    ? mc.prob_goal + "%"
                    : "—"
                }
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  `;
}
// ─── RICH PORTFOLIO PRESENTATION HELPERS ─────────────────────────────────────

function moneyFmt(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return "JMD " + n.toLocaleString(undefined, {maximumFractionDigits:0});
}

function pctFmt(value) {
  if (value == null || value === "") return "—";
  if (typeof value === "string" && value.includes("%")) return value;
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(1) + "%" : "—";
}

function getMonteCarlo() {
  const mc = state.report?.monte_carlo || state.report?.metrics?.monte_carlo || {};
  return {
    ...mc,
    prob_goal:     mc.prob_goal     ?? mc.success_rate   ?? mc.prob_double,
    median_final:  mc.median_final  ?? mc.median_wealth,
    p10_final:     mc.p10_final     ?? mc.p10_wealth     ?? mc.expected_shortfall_10pct,
    p90_final:     mc.p90_final     ?? mc.p90_wealth,
    prob_preserve: mc.prob_preserve ?? mc.prob_loss,
    horizon_years: mc.horizon_years ?? mc.years,
    n_simulations: mc.n_simulations ?? mc.simulations,
  };
}

function getClassAllocation() {
  if (state.report?.class_allocation?.length) {
    return state.report.class_allocation.map(x => ({label: x.class||x.label, pct: x.pct}));
  }
  const totals = {};
  (state.report?.allocations||[]).forEach(a => {
    const cls = a.class||"Other";
    totals[cls] = (totals[cls]||0) + Number(a.pct||0);
  });
  return Object.entries(totals)
    .map(([label,pct]) => ({label, pct: Number(pct.toFixed(1))}))
    .sort((a,b) => b.pct - a.pct);
}

function getSummaryCardHTML(profile, metrics, confidence, mc) {
  const divPct = Math.round((confidence?.breakdown?.diversification?.pts||0)/(confidence?.breakdown?.diversification?.max||25)*100);
  const strategy = {Conservative:"Capital Preservation + Income",Moderate:"Growth + Stability",Aggressive:"Maximum Growth"}[profile]||"Optimised";
  const horizon  = {Conservative:"Short to Medium Term",Moderate:"Medium to Long Term",Aggressive:"Long Term"}[profile]||"Medium Term";
  const items = [
    ["📈 Expected Return", metrics.expected_return||"—", "#10B981"],
    ["📊 Risk Level",      profile,                      "var(--teal)"],
    ["🕐 Horizon",         horizon,                      "var(--text)"],
    ["🔀 Diversification", divPct+"/100",                "var(--teal)"],
    ["⚡ Strategy",        strategy,                     "var(--text)"],
    ["🎯 Confidence",      (confidence?.score||"—")+"/100 ("+(confidence?.grade||"—")+")", "var(--teal)"],
  ];
  return `<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
    ${items.map(([lbl,val,col]) => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 12px;background:var(--surface-2);border:1px solid var(--border);border-radius:10px">
        <span style="font-size:12px;color:var(--text-muted)">${lbl}</span>
        <strong style="font-size:12px;color:${col};text-align:right">${val}</strong>
      </div>`).join("")}
  </div>`;
}

function getRiskMeterHTML(profile) {
  const idx   = ["Conservative","Moderate","Aggressive"].indexOf(profile);
  const pct   = idx===0?16:idx===2?84:50;
  const color = idx===0?"#10B981":idx===2?"#EF4444":"#F59E0B";
  const desc  = {
    Conservative: "Your portfolio prioritises stability. Lower volatility with steady, moderate growth — suitable for capital preservation and near-term goals.",
    Moderate:     "Balanced growth and stability. You can handle moderate market swings in exchange for better long-term returns.",
    Aggressive:   "Growth-focused with higher volatility. Strong long-term potential for investors comfortable with significant market swings."
  }[profile]||"";
  return `<div>
    <div style="display:flex;justify-content:space-between;font-size:11px;font-weight:700;color:var(--text-muted);margin-bottom:8px">
      <span>🟢 Conservative</span><span>🟡 Moderate</span><span>🔴 Aggressive</span>
    </div>
    <div style="height:10px;background:linear-gradient(90deg,#10B981,#F59E0B,#EF4444);border-radius:999px;position:relative;margin-bottom:12px">
      <div style="position:absolute;top:-4px;left:${pct}%;transform:translateX(-50%);width:18px;height:18px;background:${color};border:3px solid white;border-radius:50%;box-shadow:0 2px 8px rgba(0,0,0,0.2)"></div>
    </div>
    <p style="font-size:13px;color:var(--text-muted);line-height:1.65">${desc}</p>
  </div>`;
}

function getProjectionHTML(expectedReturnStr, initialCapital) {
  const r  = parseFloat(expectedReturnStr)/100 || 0.10;
  const c0 = initialCapital || 100000;
  const fmt = n => "JMD " + Math.round(n).toLocaleString();
  return `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px">
    ${[["1 Year",c0*Math.pow(1+r,1),"#10B981"],["3 Years",c0*Math.pow(1+r,3),"#0BB8A9"],["5 Years",c0*Math.pow(1+r,5),"#3B82F6"],["10 Years",c0*Math.pow(1+r,10),"#8B5CF6"]].map(([lbl,val,col]) => `
      <div style="background:var(--surface-2);border:1px solid var(--border);border-radius:12px;padding:14px;text-align:center">
        <div style="font-size:11px;font-weight:700;color:var(--text-muted);margin-bottom:6px">${lbl}</div>
        <div style="font-size:15px;font-weight:800;color:${col}">${fmt(val)}</div>
      </div>`).join("")}
  </div>
  <p style="font-size:11px;color:#9CA3AF;margin-top:8px">* Illustrative only. Based on ${(r*100).toFixed(1)}% p.a. Actual results vary.</p>`;
}

function getScenarioHTML(ret_str, vol_str) {
  const r = parseFloat(ret_str)/100||0.10, v = parseFloat(vol_str)/100||0.10;
  return `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">
    ${[
      ["📈","Strong Market",  ((r+v*1.5)*100).toFixed(1), "rgba(16,185,129,0.08)","rgba(16,185,129,0.25)","#10B981","Above-average conditions"],
      ["⚖️","Typical Year",   (r*100).toFixed(1),          "rgba(245,158,11,0.08)", "rgba(245,158,11,0.25)", "#F59E0B","Normal market conditions"],
      ["📉","Weak Market",    ((r-v*1.5)*100).toFixed(1), "rgba(239,68,68,0.08)",  "rgba(239,68,68,0.25)",  "#EF4444","Below-average conditions"]
    ].map(([icon,lbl,val,bg,brd,col,sub]) => `
      <div style="background:${bg};border:1px solid ${brd};border-radius:12px;padding:16px">
        <div style="font-size:18px;margin-bottom:6px">${icon}</div>
        <div style="font-size:12px;font-weight:700;color:var(--text);margin-bottom:4px">${lbl}</div>
        <div style="font-size:22px;font-weight:800;color:${col}">${parseFloat(val)>=0?"+":""}${val}%</div>
        <div style="font-size:11px;color:#6B7280;margin-top:4px">${sub}</div>
      </div>`).join("")}
  </div>`;
}

function getWhyFitsHTML(answers, profile, bflags) {
  const reasons = [];
  if (profile) reasons.push(`Questionnaire scoring mapped you to a <strong>${profile}</strong> risk profile.`);
  if (answers?.primary_goal) reasons.push(`Primary goal is <strong>${esc(answers.primary_goal)}</strong> — this shaped the asset class weighting.`);
  if (answers?.income_loss_runway) reasons.push(`Income runway of <strong>${esc(answers.income_loss_runway)}</strong> influenced the liquidity allocation.`);
  if (answers?.earn_currency) reasons.push(`You earn in <strong>${esc(answers.earn_currency)}</strong> — JMD vs USD exposure adjusted accordingly.`);
  if (answers?.inflation_impact && answers.inflation_impact!=="Not sure")
    reasons.push(`Inflation sensitivity is <strong>${esc(answers.inflation_impact)}</strong> — inflation-hedging assets were considered.`);
  const flagKeys = Object.keys(bflags||{}).filter(k => bflags[k]?.detected);
  if (flagKeys.length) reasons.push(`Behavioral analysis detected <strong>${flagKeys.map(k=>k.replace(/_/g," ")).join(", ")}</strong> — portfolio adjusted.`);
  const suitFor = {
    Conservative: ["First-time investors","Capital preservation seekers","Short to medium horizons"],
    Moderate:     ["Young professionals","Medium to long-term planners","Balanced growth seekers"],
    Aggressive:   ["Long-term growth investors","Experienced investors","High risk tolerance"]
  }[profile]||[];
  return `<div style="display:flex;flex-direction:column;gap:10px;margin-bottom:16px">
    ${reasons.map(r => `<div style="display:flex;align-items:flex-start;gap:10px;font-size:13px;line-height:1.65">
      <span style="color:var(--teal);font-size:15px;flex-shrink:0">✔</span><span>${r}</span>
    </div>`).join("")}
  </div>
  ${suitFor.length ? `<div style="background:rgba(11,184,169,0.06);border:1px solid rgba(11,184,169,0.2);border-radius:10px;padding:12px">
    <div style="font-size:11px;font-weight:800;color:var(--teal);margin-bottom:6px">SUITABLE FOR</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px">${suitFor.map(s=>`<span style="font-size:12px;color:var(--teal);background:white;border:1px solid rgba(11,184,169,0.3);padding:3px 10px;border-radius:999px">✔ ${s}</span>`).join("")}</div>
  </div>` : ""}`;
}

function getClassExplanationHTML(classAlloc) {
  const exp = {
    "Cash":         "Liquid instruments providing stability and covering near-term withdrawal needs.",
    "Fixed Income": "Bond-like instruments generating steady income and reducing overall portfolio volatility.",
    "Equity":       "Growth-oriented holdings with higher return potential and higher market fluctuation.",
    "Real Estate":  "Property-linked exposure providing income and inflation resilience.",
    "Alternatives": "Non-traditional exposure improving diversification.",
    "Commodities":  "Inflation-sensitive assets that behave differently from stocks and bonds."
  };
  return (classAlloc||[]).map(({label,pct}) => `
    <div style="display:flex;gap:14px;align-items:flex-start;padding:12px;border-radius:10px;background:var(--surface-2);border:1px solid var(--border)">
      <div style="width:38px;height:38px;border-radius:8px;background:rgba(11,184,169,0.08);border:1px solid rgba(11,184,169,0.2);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;color:var(--teal);flex-shrink:0">${pct}%</div>
      <div>
        <div style="font-size:13px;font-weight:700;color:var(--text);margin-bottom:3px">${esc(label)}</div>
        <div style="font-size:12px;color:var(--text-muted);line-height:1.6">${exp[label]||"Contributes to portfolio diversification and risk management."}</div>
      </div>
    </div>`).join("");
}

function getRecommendationsHTML(profile, answers) {
  const freq = answers?.review_frequency || "Quarterly";
  return [
    `Rebalance <strong>${freq.toLowerCase()}</strong> or when any asset class drifts more than 5% from its target weight.`,
    "Avoid panic-selling during downturns — volatility is a normal, expected part of investing.",
    "Review your financial goals annually to ensure the portfolio still matches your life situation.",
    "Maintain 3–6 months of living expenses in accessible savings before increasing investments.",
    profile==="Conservative" ? "Consider gradually increasing equity exposure as your emergency fund strengthens." :
    profile==="Aggressive"   ? "Monitor concentration — no single sector should exceed 30% of your equity allocation." :
                               "As income grows, increase contributions consistently to benefit from compounding returns.",
    "When rebalancing, consider tax implications — selling winners can trigger capital gains."
  ].map(r => `
    <div style="display:flex;align-items:flex-start;gap:10px;font-size:13px;color:var(--text);line-height:1.65;padding:10px 0;border-bottom:1px solid var(--border)">
      <span style="color:var(--teal);font-size:14px;flex-shrink:0">📌</span>
      <span>${r}</span>
    </div>`).join("");
}

// ─── PORTFOLIO VIEW ─────────────────────────────────────────────────────────
// ─── PORTFOLIO VIEW ─────────────────────────────────────────────────────────
function renderPortfolio(mount) {

  if (!state.report?.allocations?.length) {

    mount.innerHTML = `
      <section class="panel">
        <div class="empty-state">
          <div class="empty-icon">📊</div>
          <div class="empty-h">
            No Portfolio Yet
          </div>
          <p class="empty-p">
            Chat with Barita Bear to generate your personalised portfolio.
          </p>
          <button class="btn-action" onclick="switchView('advisor')">
            🐻 Start AI Chatbot →
          </button>
        </div>
      </section>
    `;

    return;
  }

  const report = state.report;
  const allocations = report.allocations || [];
  const metrics = report.metrics || {};
  const profile =
    report.behavioral_profile ||
    report.profile ||
    "Moderate";

  const confidence = report.confidence || {};
  const mc = getMonteCarlo();
  const classAlloc = report.class_allocation || getClassAllocation();

  const candidates =
    report.optimizer_comparison ||
    metrics.candidate_portfolios ||
    [];

  const method =
    metrics.optimization_method ||
    report.optimization_method ||
    metrics.mvo_strategy ||
    report.mvo_strategy ||
    "Optimised";

  const optSummary =
    report.optimizer_summary ||
    metrics.optimizer_summary ||
    metrics.optimization_explanation ||
    report.engine_explanation ||
    "The system used your questionnaire answers, Dimension Depths asset data, covariance, correlations, and risk suitability logic to generate this recommendation.";

  const name =
    state.user?.displayName?.split(" ")[0] ||
    state.answers?.first_name ||
    "Investor";

  mount.innerHTML = `
    <section style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;gap:14px;flex-wrap:wrap">
      <div>
        <h2 style="font-family:var(--font-display);font-size:24px;font-weight:800;color:var(--text);margin-bottom:6px">
          ${esc(name)}'s Investment Portfolio
          <span class="profile-badge ${String(profile).toLowerCase()}" style="margin-left:10px">
            ${esc(profile)}
          </span>
        </h2>

        <p style="font-size:13px;color:var(--text-muted)">
          Built using risk profiling, behavioural suitability logic, Dimension Depths data, MVO, HRP, Black-Litterman-style views, and Monte Carlo validation.
        </p>
      </div>

      <button class="btn-dl" id="btn-dl-main">
        ⬇ Download Full Report
      </button>
    </section>

    <section class="stat-grid">
      <div class="stat-card">
        <div class="stat-card-label">Confidence Score</div>
        <div class="stat-card-val" style="color:var(--teal)">
          ${confidence.score ?? "—"}/100
        </div>
        <div class="stat-card-sub">
          ${esc(confidence.label || "Portfolio suitability match")}
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-card-label">Expected Return</div>
        <div class="stat-card-val" style="color:var(--green)">
          ${metrics.expected_return || "—"}
        </div>
        <div class="stat-card-sub">Annualised estimate</div>
      </div>

      <div class="stat-card">
        <div class="stat-card-label">Volatility</div>
        <div class="stat-card-val" style="color:var(--red)">
          ${metrics.volatility || "—"}
        </div>
        <div class="stat-card-sub">Risk / annual swings</div>
      </div>

      <div class="stat-card">
        <div class="stat-card-label">Sharpe Ratio</div>
        <div class="stat-card-val" style="color:var(--teal)">
          ${metrics.sharpe_ratio || "—"}
        </div>
        <div class="stat-card-sub">Return per unit risk</div>
      </div>
    </section>

    <section class="panel" style="margin-bottom:22px">
      <div class="panel-header">
        <div>
          <div class="panel-title">🎚️ Risk Level</div>
          <div class="panel-sub">Your position on the risk spectrum</div>
        </div>
      </div>
      <div class="panel-body">
        ${getRiskMeterHTML(profile)}
      </div>
    </section>

    <section class="panel" style="margin-bottom:22px">
      <div class="panel-header">
        <div>
          <div class="panel-title">💰 What Happens to JMD 100,000?</div>
          <div class="panel-sub">Simple projection for beginner investors</div>
        </div>
      </div>
      <div class="panel-body">
        ${getProjectionHTML(metrics.expected_return, 100000)}
      </div>
    </section>

    <section class="panel" style="margin-bottom:22px">
      <div class="panel-header">
        <div>
          <div class="panel-title">🔭 Scenario Analysis</div>
          <div class="panel-sub">How your portfolio may behave in different markets</div>
        </div>
      </div>
      <div class="panel-body">
        ${getScenarioHTML(metrics.expected_return, metrics.volatility)}
      </div>
    </section>

    <section class="panel" style="margin-bottom:22px;border-left:4px solid var(--teal)">
      <div class="panel-header">
        <div>
          <div class="panel-title">🧠 Why This Portfolio Was Chosen</div>
          <div class="panel-sub">Selected method: ${esc(method)}</div>
        </div>
      </div>

      <div class="panel-body">
        <p style="font-size:14px;line-height:1.75;color:var(--text);margin-bottom:16px">
          ${esc(optSummary)}
        </p>

        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px">
          <div style="background:var(--surface-2);border:1px solid var(--border);border-radius:12px;padding:14px">
            <div style="font-size:12px;font-weight:800;color:var(--text)">MVO</div>
            <div style="font-size:12px;color:var(--text-muted);line-height:1.5;margin-top:4px">
              Finds efficient risk-return weights.
            </div>
          </div>

          <div style="background:var(--surface-2);border:1px solid var(--border);border-radius:12px;padding:14px">
            <div style="font-size:12px;font-weight:800;color:var(--text)">Black-Litterman</div>
            <div style="font-size:12px;color:var(--text-muted);line-height:1.5;margin-top:4px">
              Tilts expected returns using investor views.
            </div>
          </div>

          <div style="background:var(--surface-2);border:1px solid var(--border);border-radius:12px;padding:14px">
            <div style="font-size:12px;font-weight:800;color:var(--text)">HRP</div>
            <div style="font-size:12px;color:var(--text-muted);line-height:1.5;margin-top:4px">
              Tests correlation-based diversification.
            </div>
          </div>

          <div style="background:var(--surface-2);border:1px solid var(--border);border-radius:12px;padding:14px">
            <div style="font-size:12px;font-weight:800;color:var(--text)">Monte Carlo</div>
            <div style="font-size:12px;color:var(--text-muted);line-height:1.5;margin-top:4px">
              Stress-tests possible future outcomes.
            </div>
          </div>
        </div>
      </div>
    </section>

    ${
      candidates.length
        ? `
          <section class="panel" style="margin-bottom:22px">
            <div class="panel-header">
              <div>
                <div class="panel-title">🔬 Optimizer Comparison</div>
                <div class="panel-sub">
                  The engine tested candidate portfolios and selected the best match.
                </div>
              </div>
            </div>

            <div class="panel-body">
              <canvas id="candidate-chart" height="80" style="margin-bottom:18px"></canvas>

              <table class="fi-table">
                <thead>
                  <tr>
                    <th>Method Tested</th>
                    <th>Expected Return</th>
                    <th>Volatility</th>
                    <th>Sharpe</th>
                    <th>Diversification</th>
                    <th>Selected</th>
                  </tr>
                </thead>

                <tbody>
                  ${candidates.map(c => `
                    <tr>
                      <td>${esc(c.method || c.name || "Method")}</td>
                      <td>${pctFmt(c.expected_return)}</td>
                      <td>${pctFmt(c.volatility)}</td>
                      <td>${esc(c.sharpe ?? "—")}</td>
                      <td>${esc(c.diversification ?? "—")}</td>
                      <td>${c.selected ? "✓ Yes" : "—"}</td>
                    </tr>
                  `).join("")}
                </tbody>
              </table>
            </div>
          </section>
        `
        : ""
    }

    <section class="panel" style="margin-bottom:22px;border-left:4px solid var(--teal)">
      <div class="panel-header">
        <div>
          <div class="panel-title">💡 Why This Portfolio Fits You</div>
          <div class="panel-sub">How your answers shaped this recommendation</div>
        </div>
      </div>

      <div class="panel-body">
        ${getWhyFitsHTML(state.answers, profile, report.behavioral_flags || {})}
      </div>
    </section>

    <section class="panel" style="margin-bottom:22px">
      <div class="panel-header">
        <div>
          <div class="panel-title">📋 Full Allocation + Rationale</div>
          <div class="panel-sub">
            Each selected asset includes the reason it fits your profile.
          </div>
        </div>
      </div>

      <div class="panel-body">
        <div
          style="
            height: 320px;
            max-height: 320px;
            overflow: hidden;
            margin-bottom: 22px;
            position: relative;
          "
        >
          <canvas
            id="alloc-bar-chart"
            style="
              width:100% !important;
              height:100% !important;
              display:block;
            "
          ></canvas>
        </div>

        <div id="alloc-cards" style="display:flex;flex-direction:column;gap:12px">
          ${allocations.map((asset, index) => renderAssetCard(asset, index)).join("")}
        </div>
      </div>
    </section>

    <section class="panel" style="margin-bottom:22px">
      <div class="panel-header">
        <div>
          <div class="panel-title">📚 What Each Asset Class Does For You</div>
          <div class="panel-sub">Beginner-friendly explanation of the portfolio mix</div>
        </div>
      </div>

      <div class="panel-body">
        <div style="display:flex;flex-direction:column;gap:10px">
          ${getClassExplanationHTML(classAlloc)}
        </div>
      </div>
    </section>

    <section class="panel" style="margin-bottom:22px">
      <div class="panel-header">
        <div>
          <div class="panel-title">🎲 Monte Carlo Goal Validation</div>
          <div class="panel-sub">
            ${esc(mc.method_note || "Stress-tested across simulated market paths")}
          </div>
        </div>
      </div>

      <div class="panel-body">
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px">
          <div class="stat-card" style="box-shadow:none">
            <div class="stat-card-label">Goal Probability</div>
            <div class="stat-card-val" style="color:var(--teal)">
              ${mc.prob_goal !== undefined ? mc.prob_goal + "%" : "—"}
            </div>
            <div class="stat-card-sub">Chance of hitting target</div>
          </div>

          <div class="stat-card" style="box-shadow:none">
            <div class="stat-card-label">Capital Preservation</div>
            <div class="stat-card-val" style="color:var(--green)">
              ${mc.prob_preserve !== undefined ? mc.prob_preserve + "%" : "—"}
            </div>
            <div class="stat-card-sub">Keeps at least 90%</div>
          </div>

          <div class="stat-card" style="box-shadow:none">
            <div class="stat-card-label">Median Final Wealth</div>
            <div class="stat-card-val" style="font-size:20px">
              ${moneyFmt(mc.median_final)}
            </div>
            <div class="stat-card-sub">Middle simulated outcome</div>
          </div>

          <div class="stat-card" style="box-shadow:none">
            <div class="stat-card-label">Downside P10</div>
            <div class="stat-card-val" style="font-size:20px;color:var(--red)">
              ${moneyFmt(mc.p10_final || mc.expected_shortfall_10pct)}
            </div>
            <div class="stat-card-sub">Stress estimate</div>
          </div>
        </div>

        <canvas id="mc-outcome-chart" height="90"></canvas>
      </div>
    </section>

    <section class="panel" style="margin-bottom:22px">
      <div class="panel-header">
        <div>
          <div class="panel-title">🐻 Barita’s Advisory Note</div>
          <div class="panel-sub">Personalised recommendation explanation</div>
        </div>
      </div>

      <div class="panel-body">
        <p style="font-size:14px;line-height:1.85;color:var(--text)">
          ${esc(report.advisory_note || "This portfolio was built to match your goal, time horizon, risk comfort, currency needs, liquidity preference, and behavioural profile.")}
        </p>
      </div>
    </section>

    <section class="panel" style="margin-bottom:22px">
      <div class="panel-header">
        <div>
          <div class="panel-title">📌 Recommendations</div>
          <div class="panel-sub">What to do next with your portfolio</div>
        </div>
      </div>

      <div class="panel-body">
        ${getRecommendationsHTML(profile, state.answers)}
      </div>
    </section>
  `;

  drawPortfolioCharts({
    allocations,
    classAlloc,
    candidates,
    mc
  });

  document
    .getElementById("btn-dl-main")
    ?.addEventListener("click", () => downloadPDF("latest"));
}

function renderAssetCard(asset, index) {

  const color =
    asset.color ||
    [
      "#0BB8A9",
      "#3B82F6",
      "#F59E0B",
      "#10B981",
      "#EF4444",
      "#8B5CF6"
    ][index % 6];

  return `
    <div style="display:flex;align-items:flex-start;gap:14px;padding:15px 16px;border-radius:12px;background:var(--surface-2);border:1px solid var(--border)">
      <div style="width:10px;height:48px;border-radius:999px;background:${color};flex-shrink:0"></div>

      <div style="flex:1;min-width:0">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:5px">
          <strong style="font-size:14px;color:var(--text)">
            ${esc(asset.label || asset.ticker || "Asset")}
          </strong>

          <span style="font-size:11px;color:var(--text-faint);background:var(--border);padding:2px 8px;border-radius:999px">
            ${esc(asset.ticker || "")}
          </span>

          <span style="font-size:11px;color:var(--teal);background:var(--teal-glow);padding:2px 8px;border-radius:999px">
            ${esc(asset.class || "Asset")}
          </span>
        </div>

        <p style="font-size:12px;color:var(--text-muted);line-height:1.65">
          ${esc(asset.rationale || "Selected because it improves suitability, diversification, or risk-return balance for your profile.")}
        </p>

        <div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:10px;font-size:11px;color:var(--text-muted)">
          <span>
            Expected return:
            <strong>${pctFmt(asset.expected_return)}</strong>
          </span>

          <span>
            Volatility:
            <strong>${pctFmt(asset.volatility)}</strong>
          </span>

          <span>
            Diversification penalty:
            <strong>${asset.corr_penalty ?? "—"}</strong>
          </span>
        </div>
      </div>

      <div style="text-align:right;flex-shrink:0">
        <div style="font-family:var(--font-display);font-size:22px;font-weight:800;color:${color}">
          ${pctFmt(asset.pct)}
        </div>
        <div style="font-size:11px;color:var(--text-faint)">
          of portfolio
        </div>
      </div>
    </div>
  `;
}

function drawPortfolioCharts({ allocations, classAlloc, candidates, mc }) {

  const colors = [
    "#67b80b",
    "#3B82F6",
    "#F59E0B",
    "#1010b9",
    "#EF4444",
    "#8B5CF6",
    "#EC4899",
    "#eff704"
  ];

  const bar = document.getElementById("alloc-bar-chart");

  if (bar && typeof Chart !== "undefined") {
    new Chart(bar.getContext("2d"), {
      type: "bar",
      data: {
        labels: allocations.map(a => a.ticker || a.label),
        datasets: [
          {
            data: allocations.map(a => Number(a.pct || 0)),
            backgroundColor: allocations.map((a, i) => a.color || colors[i % colors.length]),
            borderRadius: 7,
            borderWidth: 0
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        aspectRatio: 2,
        animation: false,
        plugins: {
          legend: {
            display: false
          }
        },
        scales: {
          y: {
            ticks: {
              callback: v => v + "%"
            }
          }
        }
      }
    });
  }

  const candidateChart = document.getElementById("candidate-chart");

  if (
    candidateChart &&
    typeof Chart !== "undefined" &&
    candidates.length
  ) {
    new Chart(candidateChart.getContext("2d"), {
      type: "bar",
      data: {
        labels: candidates.map(c => c.method || c.name || "Method"),
        datasets: [
          {
            label: "Return %",
            data: candidates.map(c => Number(c.expected_return || 0)),
            borderRadius: 7,
            borderWidth: 0
          },
          {
            label: "Volatility %",
            data: candidates.map(c => Number(c.volatility || 0)),
            borderRadius: 7,
            borderWidth: 0
          }
        ]
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            position: "top"
          }
        },
        scales: {
          y: {
            ticks: {
              callback: v => v + "%"
            }
          }
        }
      }
    });
  }

  const mcChart = document.getElementById("mc-outcome-chart");

  if (
    mcChart &&
    typeof Chart !== "undefined" &&
    (mc.p10_final || mc.median_final || mc.p90_final)
  ) {
    new Chart(mcChart.getContext("2d"), {
      type: "bar",
      data: {
        labels: [
          "Downside P10",
          "Median",
          "Upside P90"
        ],
        datasets: [
          {
            label: "Final Wealth",
            data: [
              Number(mc.p10_final || mc.expected_shortfall_10pct || 0),
              Number(mc.median_final || 0),
              Number(mc.p90_final || 0)
            ],
            borderRadius: 8,
            borderWidth: 0
          }
        ]
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            callbacks: {
              label: ctx => moneyFmt(ctx.raw)
            }
          }
        },
        scales: {
          y: {
            ticks: {
              callback: v => "JMD " + (v / 1000).toFixed(0) + "K"
            }
          }
        }
      }
    });
  }
}


// ─── ADVISOR / CHATBOT VIEW ─────────────────────────────────────────────────
function renderAdvisor(mount) {

  const hasReport =
    !!state.report?.allocations?.length;

  const profile =
    state.report?.behavioral_profile ||
    state.report?.profile ||
    null;

  const progress =
    Math.min(
      100,
      Math.round(
        (Object.keys(state.answers || {}).length / 24) * 100
      )
    );

  mount.innerHTML = `
    <style>
      .bear-chat-wrap {
        max-width: 860px;
        display: flex;
        flex-direction: column;
        height: calc(100vh - 170px);
        min-height: 560px;
        margin: 0 auto;
      }

      .bear-chat-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 14px;
        padding: 18px 22px;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 16px 16px 0 0;
      }

      .bear-chat-header-left {
        display: flex;
        align-items: center;
        gap: 12px;
      }

      .bear-avatar-lg {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        background: #FDF6EC;
        border: 2px solid #FEF3C7;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 27px;
        box-shadow: 0 2px 8px rgba(245,158,11,.2);
        flex-shrink: 0;
      }

      .bear-chat-name {
        font-family: var(--font-display);
        font-size: 17px;
        font-weight: 800;
        color: var(--text);
      }

      .bear-chat-sub {
        font-size: 12px;
        color: var(--text-muted);
        margin-top: 2px;
      }

      .bear-online {
        display: flex;
        align-items: center;
        gap: 5px;
        font-size: 11px;
        font-weight: 700;
        color: var(--green);
      }

      .bear-online-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: var(--green);
        animation: pulse 2s infinite;
      }

      .bear-progress {
        min-width: 140px;
      }

      .bear-mode-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        border: 1px solid var(--teal-border);
        background: var(--teal-glow);
        color: var(--teal);
        border-radius: 999px;
        padding: 6px 12px;
        font-size: 11px;
        font-weight: 800;
      }

      .bear-progress-track {
        height: 6px;
        background: var(--border);
        border-radius: 999px;
        overflow: hidden;
        margin-top: 5px;
      }

      .bear-progress-fill {
        height: 100%;
        background: var(--teal);
        width: ${hasReport ? 100 : progress}%;
        transition: width .35s ease;
      }

      .bear-messages {
        flex: 1;
        overflow-y: auto;
        padding: 22px;
        display: flex;
        flex-direction: column;
        gap: 14px;
        background: var(--surface-2);
        border-left: 1px solid var(--border);
        border-right: 1px solid var(--border);
      }

      .bear-messages::-webkit-scrollbar {
        width: 4px;
      }

      .bear-messages::-webkit-scrollbar-thumb {
        background: var(--border);
        border-radius: 2px;
      }

      .bmsg-bear {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        animation: msgIn .35s cubic-bezier(.22,1,.36,1) both;
      }

      .bmsg-user {
        display: flex;
        justify-content: flex-end;
        animation: msgIn .3s ease both;
      }

      @keyframes msgIn {
        from {
          opacity: 0;
          transform: translateY(10px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }

      @keyframes pulse {
        0%, 100% {
          opacity: 1;
        }
        50% {
          opacity: .45;
        }
      }

      .bmsg-bear-av {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: #FDF6EC;
        border: 1.5px solid #FEF3C7;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 19px;
        flex-shrink: 0;
      }

      .bmsg-bear-bubble {
        background: var(--surface);
        border: 1.5px solid var(--border);
        border-radius: 18px 18px 18px 4px;
        padding: 12px 16px;
        max-width: 78%;
        font-size: 14px;
        line-height: 1.7;
        color: var(--text);
        box-shadow: 0 1px 4px rgba(0,0,0,.04);
      }

      .bmsg-bear-bubble strong {
        color: var(--teal);
      }

      .bmsg-user-bubble {
        background: var(--teal);
        color: white;
        border-radius: 18px 18px 4px 18px;
        padding: 11px 16px;
        max-width: 72%;
        font-size: 14px;
        line-height: 1.65;
        box-shadow: 0 4px 12px rgba(11,184,169,.25);
      }

      .edit-answer-btn {
        background: var(--surface);
        border: 1px solid var(--border);
        color: var(--text-muted);
        border-radius: 999px;
        padding: 5px 10px;
        font-size: 11px;
        font-weight: 700;
        cursor: pointer;
        margin-right: 8px;
      }

      .edit-answer-btn:hover {
        color: var(--teal);
        border-color: var(--teal);
      }

      .bear-options {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-left: 46px;
        margin-top: 2px;
        animation: msgIn .35s .05s ease both;
      }

      .bear-opt-btn {
        background: var(--surface);
        border: 1.5px solid var(--border);
        border-radius: 11px;
        padding: 10px 16px;
        font-family: 'DM Sans', sans-serif;
        font-size: 13px;
        font-weight: 600;
        color: var(--text);
        cursor: pointer;
        text-align: left;
        transition: all .18s;
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .bear-opt-btn:hover {
        border-color: var(--teal);
        background: var(--teal-glow);
        color: var(--teal);
        transform: translateX(3px);
      }

      .bear-opt-btn.selected {
        border-color: var(--teal);
        background: var(--teal-glow);
        color: var(--teal);
      }

      .opt-check {
        width: 17px;
        height: 17px;
        border-radius: 50%;
        border: 1.5px solid var(--border);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 9px;
        flex-shrink: 0;
      }

      .bear-opt-btn.selected .opt-check {
        background: var(--teal);
        border-color: var(--teal);
        color: white;
      }

      .bear-typing {
        display: flex;
        gap: 4px;
        align-items: center;
        padding: 4px 0;
      }

      .bear-typing-dot {
        width: 6px;
        height: 6px;
        background: var(--text-faint);
        border-radius: 50%;
        animation: typeBounce 1.3s infinite ease-in-out;
      }

      .bear-typing-dot:nth-child(2) {
        animation-delay: .22s;
      }

      .bear-typing-dot:nth-child(3) {
        animation-delay: .44s;
      }

      @keyframes typeBounce {
        0%, 80%, 100% {
          transform: scale(.4);
          opacity: .4;
        }
        40% {
          transform: scale(1);
          opacity: 1;
        }
      }

      .bear-input-row {
        display: flex;
        gap: 10px;
        padding: 14px 18px;
        background: var(--surface);
        border: 1px solid var(--border);
        border-top: none;
        border-radius: 0 0 16px 16px;
      }

      .bear-text-input {
        flex: 1;
        background: var(--surface-2);
        border: 1.5px solid var(--border);
        border-radius: 24px;
        padding: 11px 18px;
        font-family: 'DM Sans', sans-serif;
        font-size: 14px;
        color: var(--text);
        outline: none;
        resize: none;
        min-height: 44px;
        max-height: 100px;
        line-height: 1.5;
      }

      .bear-text-input:focus {
        border-color: var(--teal);
        box-shadow: 0 0 0 3px rgba(11,184,169,.1);
      }

      .bear-send-btn {
        width: 44px;
        height: 44px;
        background: var(--teal);
        border: none;
        border-radius: 50%;
        color: white;
        font-size: 18px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all .2s;
        flex-shrink: 0;
      }

      .bear-send-btn:hover {
        background: #089E90;
        transform: scale(1.05);
      }

      .bear-send-btn:disabled {
        opacity: .4;
        cursor: not-allowed;
        transform: none;
      }

      .completion-card {
        background: linear-gradient(135deg, var(--navy), var(--navy-mid));
        color: white;
        border-radius: 16px;
        padding: 24px;
        margin-left: 46px;
        box-shadow: var(--shadow-md);
      }

      .completion-card h3 {
        font-family: var(--font-display);
        font-size: 20px;
        margin-bottom: 8px;
      }

      .completion-card p {
        color: rgba(255,255,255,.76);
        line-height: 1.65;
        font-size: 14px;
        margin-bottom: 16px;
      }

      .completion-card button {
        width: 100%;
        border: 0;
        border-radius: 10px;
        padding: 12px 18px;
        font-weight: 800;
        cursor: pointer;
      }

      .btn-generate-chat {
        background: var(--teal);
        color: white;
        box-shadow: 0 4px 14px rgba(11,184,169,.35);
      }

      .btn-reset-chat {
        margin-top: 8px;
        background: rgba(255,255,255,.12);
        color: white;
        border: 1px solid rgba(255,255,255,.18) !important;
      }
    </style>

    <section class="bear-chat-wrap">
      <div class="bear-chat-header">
        <div class="bear-chat-header-left">
          <div class="bear-avatar-lg">
            🐻
          </div>

          <div>
            <div class="bear-chat-name">
              Barita AI Chatbot 🐾
            </div>

            <div class="bear-chat-sub">
              ${
                hasReport
                  ? "Portfolio advisor mode"
                  : "Guided profiling mode · one question at a time"
              }
            </div>
          </div>
        </div>

        <div style="display:flex;align-items:center;gap:12px">
          <div class="bear-online">
            <div class="bear-online-dot"></div>
            Online
          </div>

          ${
            hasReport && profile
              ? `<span class="profile-badge ${String(profile).toLowerCase()}" style="font-size:11px">${esc(profile)}</span>`
              : `
                <div class="bear-progress">
                  <span class="bear-mode-pill">
                    ${progress}% complete
                  </span>

                  <div class="bear-progress-track">
                    <div class="bear-progress-fill"></div>
                  </div>
                </div>
              `
          }
        </div>
      </div>

      <div class="bear-messages" id="bear-msgs"></div>

      <div class="bear-input-row">
        <textarea
          class="bear-text-input"
          id="bear-input"
          placeholder="${hasReport ? "Ask me about your portfolio… 🍯" : "Type your answer or choose an option… 🍯"}"
          rows="1"
        ></textarea>

        <button class="bear-send-btn" id="bear-send" disabled>
          →
        </button>
      </div>
    </section>
  `;

  initBearChat(hasReport);
}

function initBearChat(hasReport) {

  const inputEl = $("bear-input");
  const sendEl = $("bear-send");

  if (!inputEl || !sendEl) return;

  inputEl.addEventListener("input", () => {

    sendEl.disabled = !inputEl.value.trim();

    inputEl.style.height = "auto";
    inputEl.style.height =
      Math.min(inputEl.scrollHeight, 100) + "px";
  });

  inputEl.addEventListener("keydown", e => {

    if (e.key === "Enter" && !e.shiftKey) {

      e.preventDefault();

      bearSend();
    }
  });

  sendEl.addEventListener("click", bearSend);

  if (hasReport) {
    initAdvisorChat();
  } else {
    initQuestionnaireChat();
  }
}
// ─── CHATBOT INITIALISATION ─────────────────────────────────────────────────
function initAdvisorChat() {

  const bProfile =
    state.report?.behavioral_profile ||
    state.report?.profile ||
    "Moderate";

  const conf =
    state.report?.confidence?.score;

  const mc =
    getMonteCarlo();

  if (!state.chatHistory.length) {

    const greeting = `
🐻 Hey ${esc(state.answers?.first_name || "there")}! Pawsome — your portfolio is ready.

You are a **${bProfile}** investor${conf ? ` with a confidence score of **${conf}/100**` : ""}.

${mc.prob_goal !== undefined ? `Monte Carlo gives a **${mc.prob_goal}% chance** of reaching your target over the selected horizon.` : ""}

Ask me why I chose an asset, what your risk means, how Monte Carlo works, or how to read your report.
    `.trim();

    bearAddMessage(greeting, null, false);

    state.chatHistory.push({
      role: "advisor",
      text: greeting
    });

    saveLocalSession();

  } else {

    state.chatHistory.forEach((msg, index) => {

      if (msg.role === "advisor" || msg.role === "bear") {
        bearAddMessage(
          msg.text,
          msg.options || null,
          false,
          false
        );
      }

      if (msg.role === "user") {
        bearAddUserMessage(
          msg.text,
          false,
          index
        );
      }
    });
  }

  bearScroll();
}

async function initQuestionnaireChat() {

  state.chatHistory = state.chatHistory || [];

  if (state.chatHistory.length) {

    state.chatHistory.forEach((msg, index) => {

      if (msg.role === "bear") {
        bearAddMessage(
          msg.text,
          msg.options || null,
          false,
          false
        );
      }

      if (msg.role === "user") {
        bearAddUserMessage(
          msg.text,
          false,
          index
        );
      }
    });

    updateChatProgressUI();
    bearScroll();

    return;
  }

  bearShowTyping();

  try {

    const result =
      await callQuestionnaireBot(
        "",
        "intro"
      );

    bearRemoveTyping();

    const msg =
      result?.message ||
      "🐻 Hi! I'm Barita. Let's build your personalised investment profile. What is your first name?";

    bearAddMessage(
      msg,
      result?.options || null
    );

    state.chatHistory.push({
      role: "bear",
      text: msg,
      options: result?.options || null
    });

    saveLocalSession();

  } catch (err) {

    bearRemoveTyping();

    bearAddMessage(
      `🐻 I had trouble starting the questionnaire (${err.message}). Check that Flask is running, then type your first name to continue.`,
      null
    );
  }
}

async function callQuestionnaireBot(
  message,
  stage = "questionnaire"
) {

  const data =
    await callBackend(
      "/chat_questionnaire",
      {
        message,
        history: state.chatHistory.slice(-12),
        answers: state.answers || {},
        stage
      }
    );

  return data.parsed || data;
}

// ─── CHAT UI HELPERS ────────────────────────────────────────────────────────
function bearAddMessage(
  text,
  options = null,
  scroll = true,
  save = true
) {

  const wrap = $("bear-msgs");

  if (!wrap) return;

  const row =
    document.createElement("div");

  row.className = "bmsg-bear";

  row.innerHTML = `
    <div class="bmsg-bear-av">
      🐻
    </div>

    <div class="bmsg-bear-bubble">
      ${bearFormat(text)}
    </div>
  `;

  wrap.appendChild(row);

  if (options && options.length) {

    const tray =
      document.createElement("div");

    tray.className = "bear-options";
    tray.id = "bear-options-tray";

    options.forEach(opt => {

      const btn =
        document.createElement("button");

      btn.className = "bear-opt-btn";

      btn.innerHTML = `
        <span class="opt-check"></span>
        ${esc(opt)}
      `;

      btn.addEventListener("click", () => {

        tray
          .querySelectorAll(".bear-opt-btn")
          .forEach(b => b.classList.remove("selected"));

        btn.classList.add("selected");

        btn
          .querySelector(".opt-check")
          .textContent = "✓";

        setTimeout(() => {

          tray.remove();

          bearSendText(opt);

        }, 240);
      });

      tray.appendChild(btn);
    });

    wrap.appendChild(tray);
  }

  if (scroll) {
    bearScroll();
  }
}

function bearAddUserMessage(
  text,
  scroll = true,
  historyIndex = null
) {

  const wrap = $("bear-msgs");

  if (!wrap) return;

  const row =
    document.createElement("div");

  row.className = "bmsg-user";

  const indexAttr =
    historyIndex !== null
      ? `data-history-index="${historyIndex}"`
      : "";

  row.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;justify-content:flex-end">
      <button
        class="edit-answer-btn"
        ${indexAttr}
      >
        Edit
      </button>

      <div class="bmsg-user-bubble">
        ${esc(text)}
      </div>
    </div>
  `;

  wrap.appendChild(row);

  const btn =
    row.querySelector(".edit-answer-btn");

  if (btn) {

    btn.addEventListener("click", () => {

      const idx =
        btn.dataset.historyIndex
          ? Number(btn.dataset.historyIndex)
          : state.chatHistory.findIndex(m => m.role === "user" && m.text === text);

      editAnswerAtIndex(idx);
    });
  }

  if (scroll) {
    bearScroll();
  }
}

function bearShowTyping() {

  const wrap = $("bear-msgs");

  if (!wrap) return;

  const row =
    document.createElement("div");

  row.className = "bmsg-bear";
  row.id = "bear-typing";

  row.innerHTML = `
    <div class="bmsg-bear-av">
      🐻
    </div>

    <div class="bmsg-bear-bubble">
      <div class="bear-typing">
        <div class="bear-typing-dot"></div>
        <div class="bear-typing-dot"></div>
        <div class="bear-typing-dot"></div>
      </div>
    </div>
  `;

  wrap.appendChild(row);

  bearScroll();
}

function bearRemoveTyping() {

  document
    .getElementById("bear-typing")
    ?.remove();
}

function bearScroll() {

  const wrap = $("bear-msgs");

  if (wrap) {

    setTimeout(() => {
      wrap.scrollTop = wrap.scrollHeight;
    }, 45);
  }
}

function bearFormat(text) {

  return esc(text)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br/>");
}

// ─── CHAT SEND LOGIC ────────────────────────────────────────────────────────
async function bearSend() {

  const input =
    $("bear-input");

  if (!input) return;

  const text =
    input.value.trim();

  if (!text) return;

  input.value = "";
  input.style.height = "auto";

  const sendBtn =
    $("bear-send");

  if (sendBtn) {
    sendBtn.disabled = true;
  }

  await bearSendText(text);
}

async function bearSendText(text) {

  if (!text.trim()) return;

  const userIndex = state.chatHistory.length;

  bearAddUserMessage(text, true, userIndex);

  state.chatHistory.push({
    role: "user",
    text
  });

  saveLocalSession();

  document.getElementById("bear-options-tray")?.remove();

  bearShowTyping();

  try {

    if (!state.report?.allocations?.length) {

      const result = await callQuestionnaireBot(
        text,
        "questionnaire"
      );

      bearRemoveTyping();

      if (
        result?.extracted_answer &&
        typeof result.extracted_answer === "object"
      ) {
        Object.assign(state.answers, result.extracted_answer);

        saveLocalSession();

        await saveSession();
      }

      const reply =
        result?.message ||
        "Pawsome — got it. Let's keep going!";

      bearAddMessage(
        reply,
        result?.options || null
      );

      state.chatHistory.push({
        role: "bear",
        text: reply,
        options: result?.options || null
      });

      saveLocalSession();

      if (result?.stage === "complete") {
        addChatCompletionCard();
      }

      updateChatProgressUI();

    } else {

      const data = await callBackend(
        "/chat",
        {
          message: text,
          answers: state.answers,
          report: state.report,
          history: state.chatHistory.slice(-10)
        }
      );

      const reply =
        data?.reply ||
        "🐻 I’m not sure how to answer that. Please ask me something about investing, risk, allocation, returns, or your portfolio.";

      bearRemoveTyping();

      bearAddMessage(reply, null);

      state.chatHistory.push({
        role: "advisor",
        text: reply
      });

      saveLocalSession();

      await saveSession();
    }

  } catch (err) {

    bearRemoveTyping();

    bearAddMessage(
      `Oops! Something went wrong 🐾 (${err.message}). Make sure the backend is running!`,
      null
    );
  }

  const sendBtn = $("bear-send");

  if (sendBtn) {
    sendBtn.disabled = true;
  }
}

// ─── EDIT ANSWERS ────────────────────────────────────────────────────────────
async function editAnswerAtIndex(historyIndex) {
  const msg = state.chatHistory[historyIndex];

  if (!msg || msg.role !== "user") return;

  const newAnswer = prompt("Edit your answer:", msg.text);

  if (!newAnswer || !newAnswer.trim()) return;

  const cleanAnswer = newAnswer.trim();

  // Find which question this user message belonged to
  const userMessagesBeforeThis = state.chatHistory
    .slice(0, historyIndex + 1)
    .filter(m => m.role === "user");

  const questionIndex = userMessagesBeforeThis.length - 1;
  const editedQuestion = QUESTION_FLOW[questionIndex];

  if (!editedQuestion) return;

  // Keep chat only up to BEFORE the edited user message
  state.chatHistory = state.chatHistory.slice(0, historyIndex);

  // Rebuild answers from the remaining user messages
  const remainingUserMessages = state.chatHistory.filter(m => m.role === "user");

  state.answers = {};

  remainingUserMessages.forEach((answerMsg, index) => {
    const q = QUESTION_FLOW[index];

    if (q) {
      state.answers[q.field] = answerMsg.text;
    }
  });

  // Save the edited answer into the correct field
  state.answers[editedQuestion.field] = cleanAnswer;

  // Remove old portfolio because the profile changed
  state.report = null;

  // Add the edited message back in place
  state.chatHistory.push({
    role: "user",
    text: cleanAnswer,
    edited: true
  });

  saveLocalSession();
  await saveSession();

  renderView("advisor");

  const nextQ = QUESTION_FLOW[questionIndex + 1];

  if (nextQ) {
    const reply = `Got it — I updated your answer. 🐻✨\n\nNext question: ${nextQ.question}`;

    bearAddMessage(reply, nextQ.options || null);

    state.chatHistory.push({
      role: "bear",
      text: reply,
      options: nextQ.options || null
    });

    saveLocalSession();
    await saveSession();
  } else {
    addChatCompletionCard();
  }
}

// ─── CHAT PROGRESS + COMPLETION ─────────────────────────────────────────────
function updateChatProgressUI() {

  const pct =
    Math.min(
      100,
      Math.round(
        (Object.keys(state.answers || {}).length / 24) * 100
      )
    );

  const pill =
    document.querySelector(".bear-mode-pill");

  const fill =
    document.querySelector(".bear-progress-fill");

  if (pill) {
    pill.textContent = `${pct}% complete`;
  }

  if (fill) {
    fill.style.width = pct + "%";
  }
}

function addChatCompletionCard() {

  const wrap =
    $("bear-msgs");

  if (
    !wrap ||
    document.getElementById("chat-completion-card")
  ) {
    return;
  }

  const card =
    document.createElement("div");

  card.className = "completion-card";
  card.id = "chat-completion-card";

  card.innerHTML = `
    <h3>
      🎉 Pawsome! Your profile is complete.
    </h3>

    <p>
      I have enough information to build your personalised portfolio using your goals, risk comfort, currency needs, resilience, and investment style.
    </p>

    <button
      class="btn-generate-chat"
      id="btn-chat-generate"
    >
      🚀 Build My Portfolio
    </button>

    <button
      class="btn-reset-chat"
      id="btn-chat-reset"
    >
      Start over
    </button>
  `;

  wrap.appendChild(card);

  bearScroll();

  document
    .getElementById("btn-chat-generate")
    ?.addEventListener(
      "click",
      generatePortfolioFromChat
    );

  document
    .getElementById("btn-chat-reset")
    ?.addEventListener("click", () => {

      state.answers = {};
      state.report = null;
      state.chatHistory = [];
      state.qStep = 0;

      saveLocalSession();

      renderView("advisor");
    });
}

// ─── DETERMINISTIC ADVISOR REPLIES ──────────────────────────────────────────
function generateDeterministicAdvisorReply(message) {
  const msg = String(message || "").toLowerCase();
  const report = state.report || {};
  const metrics = report.metrics || {};
  const mc = getMonteCarlo();

  const profile =
    report.behavioral_profile ||
    report.profile ||
    "Moderate";

  const goal =
    state.answers?.primary_goal ||
    "your stated financial goal";

  const horizon =
    state.answers?.time_horizon ||
    "your selected time horizon";

  const topAssets = (report.allocations || [])
    .slice(0, 4)
    .map(a => `${a.label || a.ticker} (${pctFmt(a.pct)})`)
    .join(", ");

  const method =
    metrics.optimization_method ||
    metrics.mvo_strategy ||
    report.mvo_strategy ||
    "MVO-based optimisation";

  if (msg.includes("why") || msg.includes("choose") || msg.includes("selected")) {
    return `
I selected this portfolio because your answers mapped you to a **${profile}** investor profile, with your main goal being **${goal}** and a time horizon of **${horizon}**.

The engine did not simply pick the highest-return assets. It compared expected return, volatility, diversification, asset class balance, and how each asset interacts with the others. The selected method was **${method}**, meaning the portfolio was chosen for its risk-adjusted performance rather than return alone.

Your top allocations are: **${topAssets || "the selected assets"}**.

In simple terms: the portfolio tries to give you enough growth for your goal while keeping the risk level aligned with what you said you could realistically tolerate.
    `.trim();
  }

  if (msg.includes("mvo") || msg.includes("mean") || msg.includes("variance") || msg.includes("optim")) {
    return `
MVO means **Mean-Variance Optimisation**. It tries to find the best balance between expected return and risk.

For your portfolio, the system considered:
- expected return: **${metrics.expected_return || "not available"}**
- volatility: **${metrics.volatility || "not available"}**
- Sharpe ratio: **${metrics.sharpe_ratio || "not available"}**
- asset correlations and diversification

A high-return asset is not automatically selected if it adds too much volatility or overlaps too heavily with other assets. That is why MVO is useful: it looks at the portfolio as a whole, not just each asset individually.
    `.trim();
  }

  if (msg.includes("risk") || msg.includes("volatility") || msg.includes("loss")) {
    return `
Your risk profile is **${profile}**, so the system adjusted the portfolio to match your comfort with uncertainty and possible losses.

The portfolio volatility is **${metrics.volatility || "not available"}**. Volatility estimates how much the portfolio may fluctuate over time. Lower volatility usually means a smoother ride, while higher volatility may offer more growth potential but with larger swings.

Your answers about loss tolerance, reaction to a 20% drop, financial runway, debt, and investment experience all helped shape this classification.

So this is not just a generic risk label — it is based on your responses and then reflected in the final allocation.
    `.trim();
  }

  if (msg.includes("monte") || msg.includes("simulation") || msg.includes("probability") || msg.includes("goal")) {
    return `
Monte Carlo simulation stress-tests the portfolio across many possible future outcomes instead of assuming one perfect path.

For your portfolio:
- goal probability: **${mc.prob_goal !== undefined ? mc.prob_goal + "%" : "not available"}**
- median final wealth: **${moneyFmt(mc.median_final)}**
- downside estimate: **${moneyFmt(mc.p10_final || mc.expected_shortfall_10pct)}**
- upside estimate: **${moneyFmt(mc.p90_final)}**

This helps answer: “If markets behave in many different ways, how often does this portfolio still support the client’s goal?”

That makes the recommendation more realistic than using expected return alone.
    `.trim();
  }

  if (msg.includes("asset") || msg.includes("allocation") || msg.includes("money")) {
    return `
Your money is mainly allocated across: **${topAssets || "the selected portfolio assets"}**.

Each allocation was chosen based on its role:
- fixed income/cash improves stability and liquidity
- equities support long-term growth
- real estate or alternatives may improve diversification
- currency exposure helps match earning/spending patterns

The key idea is not only “what asset looks good,” but “what combination of assets fits you best.” That is why the allocation is diversified instead of concentrated in one investment.
    `.trim();
  }

  if (msg.includes("remember") || msg.includes("my answers") || msg.includes("what did i say")) {
    return `
Yes — I am using your saved questionnaire responses in this session.

Here is what I currently remember:
- goal: **${state.answers?.primary_goal || "not answered"}**
- risk reaction: **${state.answers?.drop_reaction || "not answered"}**
- maximum loss tolerance: **${state.answers?.max_loss || "not answered"}**
- income runway: **${state.answers?.income_loss_runway || "not answered"}**
- earning currency: **${state.answers?.earn_currency || "not answered"}**
- spending currency: **${state.answers?.spend_currency || "not answered"}**
- investment style: **${state.answers?.invest_style || "not answered"}**

Those answers are used to shape both the risk profile and the portfolio recommendation.
    `.trim();
  }
if (msg.includes("divers") || msg.includes("correlation") || msg.includes("covariance")) {
  return `
Diversification is important because assets do not all move in the same way. The system uses covariance/correlation information to avoid building a portfolio where every asset behaves too similarly.

If two assets are highly correlated, adding both may not reduce risk much. If assets have lower correlation, the portfolio can sometimes reduce volatility without sacrificing too much expected return.

That is why the recommendation is not only based on the highest-return assets. It considers how each asset contributes to the total portfolio risk.
  `.trim();
}

if (msg.includes("black") || msg.includes("litterman") || msg.includes("views")) {
  return `
Black-Litterman-style adjustment helps combine market-based expectations with investor or strategy views.

In this system, it acts as a controlled tilt. Instead of blindly trusting raw expected returns, the engine adjusts assumptions based on the client’s goal, risk profile, sector preferences, and market conditions.

This makes the allocation more stable than simply ranking assets by expected return.
  `.trim();
}

if (msg.includes("hrp") || msg.includes("hierarchical") || msg.includes("cluster")) {
  return `
HRP means Hierarchical Risk Parity. It groups assets based on how similarly they behave, then allocates risk across those groups.

This is useful because traditional optimisation can become unstable when assets are highly correlated or when the covariance matrix is noisy.

In this project, HRP works as a diversification check alongside MVO and Black-Litterman-style tilting.
  `.trim();
}

// Greetings handling
if (
  msg.includes("hi") ||
  msg.includes("hello") ||
  msg.includes("hey")
) {
  return `
Hey ${state.answers?.first_name || "there"}! 🐻

I’m Barita Bear, your AI investment advisor. I can explain:
- your portfolio allocation
- risk profile
- Monte Carlo simulation
- MVO optimisation
- diversification
- expected return and volatility
- why specific assets were selected

Ask me anything about your portfolio 🍯
  `.trim();
}

// Disclaimer handling
if (
  msg.includes("financial advice") ||
  msg.includes("guarantee") ||
  msg.includes("guaranteed")
) {
  return `
This platform is designed as an educational and decision-support tool, not as guaranteed financial advice.

The portfolio recommendations are generated using optimisation models, historical market relationships, behavioural profiling, and Monte Carlo simulations. However, real markets are uncertain and future returns cannot be guaranteed.

Users should still consult a licensed financial advisor before making major investment decisions.
  `.trim();
}


// Fallback generic reply for unrecognized questions.
  return `
Pawsome question 🐻

Based on your saved profile, I would interpret this through your **${profile}** investor classification and your goal of **${goal}**.

The portfolio engine considers:
- questionnaire responses
- expected returns
- volatility
- covariance/correlation effects
- diversification
- MVO optimisation
- HRP clustering
- Monte Carlo validation
- behavioural finance indicators

The selected allocation is therefore not based on a single factor, but on how the assets work together as a portfolio.

For this client, the recommendation is mainly supported by:
- risk profile: **${profile}**
- expected return: **${metrics.expected_return || "not available"}**
- volatility: **${metrics.volatility || "not available"}**
- Sharpe ratio: **${metrics.sharpe_ratio || "not available"}**
- top allocations: **${topAssets || "the selected portfolio assets"}**

If your question relates to suitability, the key principle is that the system tries to balance return potential with the client’s actual risk tolerance, liquidity needs, behavioural responses, and financial goals.
`.trim();
}

// ─── GENERATE PORTFOLIO FROM CHAT ───────────────────────────────────────────
async function generatePortfolioFromChat() {

  const btn =
    document.getElementById("btn-chat-generate");

  if (btn) {
    btn.disabled = true;
    btn.textContent = "Building your portfolio… 🐾";
  }

  bearAddMessage(
    "Bear with me while I run the portfolio engine, diversification checks, MVO, HRP, Black-Litterman-style views, Monte Carlo, and your personalised advisory note. 🐻📊",
    null
  );

  bearShowTyping();

  try {

    const data =
      await callBackend(
        "/analyse",
        {
          answers: state.answers
        }
      );

    bearRemoveTyping();

    state.report = data;

    saveLocalSession();

    try {
      await saveSession();
    } catch (err) {
      console.warn(
        "Portfolio generated, but Firestore save was skipped:",
        err.message
      );
    }

    bearAddMessage(
      `🎉 Your portfolio is ready! You are a **${data.behavioral_profile || data.profile}** investor with a confidence score of **${data.confidence?.score || "—"}/100**. I’m taking you to your portfolio dashboard now. 🍯`,
      null
    );

    state.chatHistory.push({
      role: "bear",
      text: "Portfolio generated successfully."
    });

    saveLocalSession();

    setTimeout(() => {
      switchView("portfolio");
    }, 1200);

  } catch (err) {

    bearRemoveTyping();

    bearAddMessage(
      `Oh no — I could not build the portfolio yet (${err.message}). Please check the backend terminal for the exact error and try again.`,
      null
    );

    if (btn) {
      btn.disabled = false;
      btn.textContent = "🚀 Try Again";
    }
  }
}

// ─── REPORTS + PDF ──────────────────────────────────────────────────────────
async function downloadPDF(reportId = "latest") {

  try {

    const token =
      state.firebaseToken ||
      await state.user.getIdToken();

    const res =
      await fetch(
        `${BACKEND_URL}/generate_report`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          },
          body: JSON.stringify({
            answers: state.answers,
            report: state.report,
            report_id: reportId
          })
        }
      );

    if (!res.ok) {
      throw new Error(await res.text());
    }

    const blob =
      await res.blob();

    const url =
      URL.createObjectURL(blob);

    const a =
      document.createElement("a");

    const name =
      state.user?.displayName ||
      "Client";

    a.href = url;
    a.download =
      `Barita_Portfolio_Report_${name.replace(/\s+/g, "_")}.pdf`;

    a.click();

    URL.revokeObjectURL(url);

  } catch (err) {

    alert(
      "Failed to generate PDF: " + err.message
    );
  }
}

function renderProfile(mount) {
  const answers = state.answers || {};
  const entries = Object.entries(answers);

  const name =
    state.user?.displayName ||
    `${answers.first_name || ""} ${answers.last_name || ""}`.trim() ||
    "Investor";

  mount.innerHTML = `
    <section class="panel" style="margin-bottom:22px">
      <div class="panel-header">
        <div>
          <div class="panel-title">👤 My Profile</div>
          <div class="panel-sub">
            View and edit your saved questionnaire responses
          </div>
        </div>

        <button class="btn-action" id="btn-edit-profile">
          ✏️ Continue / Edit in Chatbot
        </button>
      </div>

      <div class="panel-body">
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:22px">
          <div style="width:58px;height:58px;border-radius:50%;background:var(--teal);color:white;display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:800">
            ${esc(name[0] || "I")}
          </div>

          <div>
            <div style="font-size:18px;font-weight:800;color:var(--text)">
              ${esc(name)}
            </div>
            <div style="font-size:13px;color:var(--text-muted)">
              ${esc(state.user?.email || "")}
            </div>
          </div>
        </div>

        ${
          entries.length
            ? `
              <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px">
                ${entries.map(([key, value]) => `
                  <div style="background:var(--surface-2);border:1px solid var(--border);border-radius:12px;padding:14px">
                    <div style="font-size:11px;font-weight:800;color:var(--text-muted);text-transform:uppercase;margin-bottom:5px">
                      ${esc(key.replaceAll("_", " "))}
                    </div>
                    <div style="font-size:14px;color:var(--text);line-height:1.5">
                      ${esc(value)}
                    </div>
                  </div>
                `).join("")}
              </div>
            `
            : `
              <div class="empty-state">
                <div class="empty-icon">🐻</div>
                <div class="empty-h">No Profile Answers Yet</div>
                <p class="empty-p">
                  Start the AI chatbot to build your investor profile.
                </p>
              </div>
            `
        }
      </div>
    </section>
  `;

  document
    .getElementById("btn-edit-profile")
    ?.addEventListener("click", () => {
      switchView("advisor");
    });
}

async function renderReports(mount) {

  mount.innerHTML = `
    <section class="panel">
      <div class="panel-header">
        <div>
          <div class="panel-title">
            Your Reports
          </div>
          <div class="panel-sub">
            Download saved portfolio reports
          </div>
        </div>
      </div>

      <div class="panel-body" id="report-list">
        <p class="empty-p">
          Loading reports…
        </p>
      </div>
    </section>
  `;

  const list =
    $("report-list");

  let reports = [];

  try {

    const q =
      query(
        collection(db, "users", state.user.uid, "reports"),
        orderBy("createdAt", "desc"),
        limit(10)
      );

    const snap =
      await getDocs(q);

    reports =
      snap.docs.map(d => ({
        id: d.id,
        ...d.data()
      }));

  } catch (err) {

    console.warn(
      "Report history unavailable:",
      err.message
    );
  }

  if (!reports.length && !state.report) {

    list.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📄</div>
        <div class="empty-h">
          No Reports Yet
        </div>
        <p class="empty-p">
          Complete the AI chatbot to generate your first portfolio report.
        </p>
        <button class="btn-action" onclick="switchView('advisor')">
          Start AI Chatbot →
        </button>
      </div>
    `;

    return;
  }

  list.innerHTML = "";

  if (state.report) {

    const item =
      document.createElement("div");

    item.className = "report-item";

    item.innerHTML = `
      <div class="report-item-left">
        <h4>
          Current Portfolio Report
        </h4>
        <p>
          ${esc(state.report.behavioral_profile || state.report.profile || "Portfolio")} · Current session
        </p>
      </div>

      <button class="btn-dl">
        ⬇ Download PDF
      </button>
    `;

    item
      .querySelector(".btn-dl")
      .addEventListener(
        "click",
        () => downloadPDF("latest")
      );

    list.appendChild(item);
  }

  reports.forEach(report => {

    const item =
      document.createElement("div");

    item.className = "report-item";

    item.innerHTML = `
      <div class="report-item-left">
        <h4>
          Saved Portfolio Report
        </h4>

        <p>
          ${esc(report.behavioral_profile || report.profile || "Portfolio")}
        </p>
      </div>

      <button class="btn-dl">
        ⬇ Download PDF
      </button>
    `;

    item
      .querySelector(".btn-dl")
      .addEventListener(
        "click",
        () => downloadPDF(report.id)
      );

    list.appendChild(item);
  });
}

// ─── MINI ALLOCATION ANIMATION ──────────────────────────────────────────────
function maybeRenderMiniAlloc() {

  document
    .querySelectorAll(".alloc-bar-inner")
    .forEach(bar => {

      if (!bar.dataset.pct) return;

      requestAnimationFrame(() => {
        bar.style.width = bar.dataset.pct + "%";
      });
    });
}



// ─── LEGACY QUESTIONNAIRE STUBS ─────────────────────────────────────────────
window.openQuestionnaire = function () {
  switchView("advisor");
};

function closeQuestionnaire() {
  $("modal-questionnaire")?.classList.add("hidden");
}

// ─── DOM EVENTS ─────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {

  document.getElementById("btn-google")
    ?.addEventListener("click", window.googleLogin);

  document.getElementById("btn-email-auth")
    ?.addEventListener("click", window.emailAuth);

  document.getElementById("btn-toggle-mode")
    ?.addEventListener("click", window.toggleRegister);

  document.getElementById("btn-forgot")
    ?.addEventListener("click", window.resetPassword);

  ["email", "password"].forEach(id => {

    document.getElementById(id)
      ?.addEventListener("keydown", e => {

        if (e.key === "Enter") {
          window.emailAuth();
        }
      });
  });
});

// ─── EXPOSE GLOBALS ─────────────────────────────────────────────────────────
window.switchView = switchView;
window.handleSignOut = window.handleSignOut;
window.downloadPDF = downloadPDF;
