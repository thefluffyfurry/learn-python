const API_BASE_URL = "https://keyquuyuamfuvotaruod.supabase.co/functions/v1/pyquest-api";
const LOCAL_PROGRESS_KEY = "pyquest_web_progress_v2";
const LOCAL_SESSION_KEY = "pyquest_web_session_v2";

const state = {
  apiAvailable: false,
  lessons: [],
  filteredLessons: [],
  leaders: [],
  activeLesson: null,
  completedIds: new Set(),
  localProgress: loadJson(LOCAL_PROGRESS_KEY, { completedIds: [], xp: 0 }),
  session: loadJson(LOCAL_SESSION_KEY, { token: "", username: "" }),
  profile: null,
};

const els = {
  modePill: byId("mode-pill"),
  apiPill: byId("api-pill"),
  authTitle: byId("auth-title"),
  authDetail: byId("auth-detail"),
  authMessage: byId("auth-message"),
  usernameInput: byId("username-input"),
  passwordInput: byId("password-input"),
  loginButton: byId("login-button"),
  signupButton: byId("signup-button"),
  logoutButton: byId("logout-button"),
  refreshButton: byId("refresh-button"),
  openNextButton: byId("open-next-button"),
  profileName: byId("profile-name"),
  profileMeta: byId("profile-meta"),
  progressBar: byId("progress-bar"),
  syncTitle: byId("sync-title"),
  syncDetail: byId("sync-detail"),
  nextLessonTitle: byId("next-lesson-title"),
  nextLessonDetail: byId("next-lesson-detail"),
  localCacheTitle: byId("local-cache-title"),
  localCacheDetail: byId("local-cache-detail"),
  topicCount: byId("topic-count"),
  lessonCount: byId("lesson-count"),
  doneCount: byId("done-count"),
  xpCount: byId("xp-count"),
  heroTrack: byId("hero-track"),
  heroTrackDetail: byId("hero-track-detail"),
  searchInput: byId("search-input"),
  filterSelect: byId("filter-select"),
  topicSelect: byId("topic-select"),
  lessonSummary: byId("lesson-summary"),
  lessonList: byId("lesson-list"),
  lessonEmpty: byId("lesson-empty"),
  lessonContent: byId("lesson-content"),
  lessonTopic: byId("lesson-topic"),
  lessonTitle: byId("lesson-title"),
  lessonSummaryDetail: byId("lesson-summary-detail"),
  lessonStage: byId("lesson-stage"),
  lessonXp: byId("lesson-xp"),
  lessonState: byId("lesson-state"),
  lessonExplanation: byId("lesson-explanation"),
  lessonCode: byId("lesson-code"),
  lessonChallenge: byId("lesson-challenge"),
  quizPrompt: byId("quiz-prompt"),
  quizOptions: byId("quiz-options"),
  quizFeedback: byId("quiz-feedback"),
  submitButton: byId("submit-button"),
  leaderboardList: byId("leaderboard-list"),
  topicProgressCaption: byId("topic-progress-caption"),
  topicSpotlightList: byId("topic-spotlight-list"),
};

boot().catch((error) => {
  console.error(error);
  setStatus(`Startup error: ${error.message}`);
});

async function boot() {
  bindEvents();
  if (state.session.username) {
    els.usernameInput.value = state.session.username;
  }
  await refreshEverything();
}

function bindEvents() {
  els.loginButton.addEventListener("click", () => authenticate("login"));
  els.signupButton.addEventListener("click", () => authenticate("signup"));
  els.logoutButton.addEventListener("click", logout);
  els.refreshButton.addEventListener("click", refreshEverything);
  els.openNextButton.addEventListener("click", openRecommendedLesson);
  els.searchInput.addEventListener("input", renderLessonList);
  els.filterSelect.addEventListener("change", renderLessonList);
  els.topicSelect.addEventListener("change", renderLessonList);
  els.submitButton.addEventListener("click", submitActiveLesson);
}

async function refreshEverything() {
  await loadLessons();
  await hydrateProfile();
  await loadLeaderboard();
  renderTopicOptions();
  renderDashboard();
  renderTopicSpotlights();
  renderLessonList();
  renderLeaderboard();
  updateAuthButtons();
}

async function apiCall(path, method = "GET", payload = null, token = state.session.token) {
  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: payload ? JSON.stringify(payload) : null,
  });

  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    throw new Error("The hosted API returned invalid JSON.");
  }

  if (!response.ok) {
    throw new Error(data.error || "Request failed.");
  }
  return data;
}

async function loadLessons() {
  try {
    const data = await apiCall("/lessons", "GET", null, "");
    state.lessons = data.lessons || [];
    state.apiAvailable = true;
    setMode("Hosted sync online", "Server lessons, auth, and leaderboard are ready.");
  } catch {
    const response = await fetch("assets/lessons.json");
    state.lessons = await response.json();
    state.apiAvailable = false;
    setMode("Browser fallback", "Hosted API is unavailable. Running from bundled lessons and local browser progress.");
  }

  if (!state.activeLesson && state.lessons.length) {
    state.activeLesson = recommendedLesson();
  }
}

async function hydrateProfile() {
  const localIds = new Set(state.localProgress.completedIds || []);
  const localXp = Number(state.localProgress.xp || 0);

  if (!state.session.token || !state.apiAvailable) {
    state.profile = null;
    state.completedIds = localIds;
    state.localProgress.completedIds = [...localIds];
    updateXp(localXp);
    return;
  }

  try {
    const profile = await apiCall("/profile");
    state.profile = profile;
    state.completedIds = new Set([...(profile.completed_lesson_ids || []), ...localIds]);
    state.localProgress.completedIds = [...state.completedIds];
    updateXp(profile.xp || 0);
    setStatus(`Signed in as ${profile.username}.`);
  } catch (error) {
    state.profile = null;
    state.session = { token: "", username: state.session.username };
    saveJson(LOCAL_SESSION_KEY, state.session);
    state.completedIds = localIds;
    updateXp(localXp);
    setStatus(error.message);
  }
}

async function loadLeaderboard() {
  if (!state.apiAvailable) {
    state.leaders = [];
    return;
  }
  try {
    const data = await apiCall("/leaderboard", "GET", null, "");
    state.leaders = data.leaders || [];
  } catch {
    state.leaders = [];
  }
}

async function authenticate(mode) {
  const username = els.usernameInput.value.trim();
  const password = els.passwordInput.value.trim();
  if (!username || !password) {
    setStatus("Enter both username and password.");
    return;
  }
  if (!state.apiAvailable) {
    setStatus("Hosted sign-in is unavailable right now. You can still study locally in the browser.");
    return;
  }

  try {
    const data = await apiCall(mode === "signup" ? "/signup" : "/login", "POST", { username, password }, "");
    state.session = { token: data.token, username: data.username };
    saveJson(LOCAL_SESSION_KEY, state.session);
    await hydrateProfile();
    await loadLeaderboard();
    renderDashboard();
    renderTopicSpotlights();
    renderLessonList();
    renderLeaderboard();
    updateAuthButtons();
  } catch (error) {
    setStatus(error.message);
  }
}

function logout() {
  state.session = { token: "", username: "" };
  state.profile = null;
  state.completedIds = new Set(state.localProgress.completedIds || []);
  saveJson(LOCAL_SESSION_KEY, state.session);
  renderDashboard();
  renderTopicSpotlights();
  renderLessonList();
  updateAuthButtons();
  setStatus("Logged out. Browser progress is still available on this device.");
}

function updateAuthButtons() {
  const signedIn = Boolean(state.profile);
  els.logoutButton.disabled = !signedIn;
}

function renderDashboard() {
  const topicGroups = groupLessonsByTopic();
  const xp = currentXp();
  const total = state.lessons.length || 1;
  const done = state.completedIds.size;
  const percent = Math.round((done / total) * 100);
  const nextLesson = recommendedLesson();

  els.topicCount.textContent = String(Object.keys(topicGroups).length);
  els.lessonCount.textContent = String(state.lessons.length);
  els.doneCount.textContent = String(done);
  els.xpCount.textContent = String(xp);
  els.progressBar.style.width = `${percent}%`;

  if (state.profile) {
    els.profileName.textContent = state.profile.username;
    els.profileMeta.textContent = `XP ${xp} | Completed ${done}/${total} | Hosted account active`;
    els.authTitle.textContent = "Hosted sync connected";
    els.authDetail.textContent = "This browser is signed in against the hosted API and still mirrors progress locally.";
    els.syncTitle.textContent = state.apiAvailable ? "Hosted sync online" : "Browser fallback active";
    els.syncDetail.textContent = state.apiAvailable
      ? "Progress saves to the hosted server and also stays readable in this browser."
      : "The hosted API is unavailable. Browser progress is still tracked locally until sync returns.";
  } else {
    els.profileName.textContent = state.session.username || "Guest learner";
    els.profileMeta.textContent = state.apiAvailable
      ? `Browse freely or sign in. Browser progress: ${done}/${total} complete.`
      : `Hosted API unavailable. Browser progress: ${done}/${total} complete.`;
    els.authTitle.textContent = state.apiAvailable ? "Hosted login" : "Local browser mode";
    els.authDetail.textContent = state.apiAvailable
      ? "Sign in to save progress to the hosted server."
      : "The hosted API is down, so the site is running from browser-only progress.";
    els.syncTitle.textContent = state.apiAvailable ? "Ready for hosted sync" : "Browser fallback active";
    els.syncDetail.textContent = state.apiAvailable
      ? "No account connected yet. Progress remains local to this browser until you sign in."
      : "Lessons still work locally in this browser without the hosted API.";
  }

  if (nextLesson) {
    els.nextLessonTitle.textContent = nextLesson.title;
    els.nextLessonDetail.textContent = `${nextLesson.topic_name} | Stage ${String(nextLesson.stage).padStart(2, "0")}`;
    els.heroTrack.textContent = nextLesson.topic_name;
    els.heroTrackDetail.textContent = nextLesson.summary;
  } else {
    els.nextLessonTitle.textContent = "All lessons complete";
    els.nextLessonDetail.textContent = "You have finished the current curriculum.";
    els.heroTrack.textContent = "Curriculum complete";
    els.heroTrackDetail.textContent = "Refresh later for new material or review lessons you have already cleared.";
  }

  els.localCacheTitle.textContent = "Browser progress cache";
  els.localCacheDetail.textContent = "Completed lessons and XP are saved in localStorage for this browser session history.";
}

function renderTopicOptions() {
  const selected = els.topicSelect.value;
  const topics = Object.keys(groupLessonsByTopic()).sort();
  els.topicSelect.innerHTML = '<option value="all">All Topics</option>';
  for (const topic of topics) {
    const option = document.createElement("option");
    option.value = topic;
    option.textContent = topic;
    els.topicSelect.append(option);
  }
  els.topicSelect.value = topics.includes(selected) ? selected : "all";
}

function renderTopicSpotlights() {
  const topicGroups = groupLessonsByTopic();
  const topics = Object.entries(topicGroups).map(([topic, lessons]) => {
    const done = lessons.filter((lesson) => state.completedIds.has(lesson.lesson_id)).length;
    return {
      topic,
      total: lessons.length,
      done,
      next: lessons.find((lesson) => !state.completedIds.has(lesson.lesson_id)) || lessons[0],
      percent: lessons.length ? Math.round((done / lessons.length) * 100) : 0,
    };
  });

  els.topicProgressCaption.textContent = topics.length
    ? `${topics.filter((topic) => topic.done > 0).length} topics have progress. Click a card to focus that track.`
    : "No topics loaded yet.";

  els.topicSpotlightList.innerHTML = "";
  for (const item of topics) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "topic-card";
    card.innerHTML = `
      <p class="panel-label">${item.done}/${item.total} complete</p>
      <strong>${item.topic}</strong>
      <p class="muted">${item.next ? item.next.title : "All lessons complete"}</p>
      <progress max="100" value="${item.percent}"></progress>
    `;
    card.addEventListener("click", () => {
      els.topicSelect.value = item.topic;
      els.filterSelect.value = "all";
      renderLessonList();
    });
    els.topicSpotlightList.append(card);
  }
}

function renderLessonList() {
  const query = els.searchInput.value.trim().toLowerCase();
  const filter = els.filterSelect.value;
  const topic = els.topicSelect.value;

  state.filteredLessons = state.lessons.filter((lesson) => {
    const done = state.completedIds.has(lesson.lesson_id);
    const matchesFilter = filter === "all" || (filter === "done" && done) || (filter === "open" && !done);
    const matchesTopic = topic === "all" || lesson.topic_name === topic;
    const haystack = `${lesson.topic_name} ${lesson.title} ${lesson.summary} ${lesson.challenge}`.toLowerCase();
    const matchesQuery = !query || haystack.includes(query);
    return matchesFilter && matchesTopic && matchesQuery;
  });

  if (!state.filteredLessons.length) {
    els.lessonList.innerHTML = '<div class="empty-state">No lessons match these filters.</div>';
    els.lessonSummary.textContent = "0 lessons shown.";
    renderLessonDetail(null);
    return;
  }

  if (!state.activeLesson || !state.filteredLessons.some((lesson) => lesson.lesson_id === state.activeLesson.lesson_id)) {
    state.activeLesson = state.filteredLessons[0];
  }

  const currentTopic = topic === "all" ? "all topics" : topic;
  els.lessonSummary.textContent = `${state.filteredLessons.length} lessons shown across ${currentTopic}. ${state.completedIds.size} completed overall.`;
  els.lessonList.innerHTML = "";

  for (const lesson of state.filteredLessons) {
    const done = state.completedIds.has(lesson.lesson_id);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `lesson-item${state.activeLesson?.lesson_id === lesson.lesson_id ? " active" : ""}`;
    button.innerHTML = `
      <p class="panel-label">${lesson.topic_name}</p>
      <h3>${lesson.title}</h3>
      <p>Stage ${String(lesson.stage).padStart(2, "0")} | ${done ? "Completed" : "Open"} | ${lesson.xp_reward} XP</p>
    `;
    button.addEventListener("click", () => {
      state.activeLesson = lesson;
      renderLessonList();
    });
    els.lessonList.append(button);
  }

  renderLessonDetail(state.activeLesson);
}

function renderLessonDetail(lesson) {
  if (!lesson) {
    els.lessonEmpty.classList.remove("hidden");
    els.lessonContent.classList.add("hidden");
    return;
  }

  els.lessonEmpty.classList.add("hidden");
  els.lessonContent.classList.remove("hidden");
  els.lessonTopic.textContent = lesson.topic_name;
  els.lessonTitle.textContent = lesson.title;
  els.lessonSummaryDetail.textContent = lesson.summary;
  els.lessonStage.textContent = `Stage ${String(lesson.stage).padStart(2, "0")}`;
  els.lessonXp.textContent = `${lesson.xp_reward} XP`;
  els.lessonState.textContent = state.completedIds.has(lesson.lesson_id) ? "Completed" : "Open";
  els.lessonExplanation.textContent = lesson.explanation;
  els.lessonCode.textContent = lesson.code_sample;
  els.lessonChallenge.textContent = lesson.challenge;
  els.quizPrompt.textContent = lesson.quiz.prompt;
  els.quizFeedback.textContent = "Choose an answer and submit.";
  els.quizOptions.innerHTML = "";

  lesson.quiz.options.forEach((option, index) => {
    const wrapper = document.createElement("label");
    wrapper.className = "quiz-option";
    wrapper.innerHTML = `
      <input type="radio" name="lesson-answer" value="${index}">
      <span>${option}</span>
    `;
    els.quizOptions.append(wrapper);
  });
}

async function submitActiveLesson() {
  const lesson = state.activeLesson;
  if (!lesson) {
    return;
  }

  const selected = document.querySelector('input[name="lesson-answer"]:checked');
  if (!selected) {
    setStatus("Choose an answer first.");
    return;
  }

  const selectedIndex = Number(selected.value);
  const correct = selectedIndex === lesson.quiz.answer_index;
  let xpGained = correct ? lesson.xp_reward : Math.max(3, Math.floor(lesson.xp_reward / 4));
  let newXp = currentXp() + xpGained;
  let explanation = lesson.quiz.explanation;

  if (state.profile && state.apiAvailable) {
    try {
      const result = await apiCall("/submit-lesson", "POST", {
        lesson_id: lesson.lesson_id,
        selected_index: selectedIndex,
      });
      xpGained = Number(result.xp_gained || 0);
      newXp = Number(result.new_xp || newXp);
      explanation = result.explanation || explanation;
      await hydrateProfile();
      await loadLeaderboard();
      renderLeaderboard();
    } catch (error) {
      setStatus(error.message);
      return;
    }
  } else if (!state.completedIds.has(lesson.lesson_id)) {
    state.completedIds.add(lesson.lesson_id);
  }

  if (!state.completedIds.has(lesson.lesson_id)) {
    state.completedIds.add(lesson.lesson_id);
  }

  state.localProgress.completedIds = [...state.completedIds];
  state.localProgress.xp = Math.max(Number(state.localProgress.xp || 0), newXp);
  saveJson(LOCAL_PROGRESS_KEY, state.localProgress);

  els.quizFeedback.textContent = `${correct ? "Correct" : "Not quite"}. XP gained: ${xpGained}. ${explanation}`;
  updateXp(Math.max(currentXp(), newXp));
  renderDashboard();
  renderTopicSpotlights();
  renderLessonList();
}

function renderLeaderboard() {
  if (!state.leaders.length) {
    els.leaderboardList.innerHTML = '<div class="empty-state">Leaderboard appears when the hosted API is online.</div>';
    return;
  }

  els.leaderboardList.innerHTML = "";
  for (const leader of state.leaders) {
    const row = document.createElement("div");
    row.className = "leader-row";
    row.innerHTML = `
      <strong>#${leader.rank}</strong>
      <strong>${leader.username}</strong>
      <span>${leader.xp} XP</span>
      <span>${leader.completed_lessons} lessons</span>
    `;
    els.leaderboardList.append(row);
  }
}

function openRecommendedLesson() {
  const lesson = recommendedLesson();
  if (!lesson) {
    return;
  }

  state.activeLesson = lesson;
  els.topicSelect.value = "all";
  els.filterSelect.value = "all";
  els.searchInput.value = "";
  renderLessonList();
  document.getElementById("lessons").scrollIntoView({ behavior: "smooth", block: "start" });
}

function recommendedLesson() {
  if (!state.lessons.length) {
    return null;
  }
  return state.lessons.find((lesson) => !state.completedIds.has(lesson.lesson_id)) || state.lessons[0];
}

function groupLessonsByTopic() {
  return state.lessons.reduce((groups, lesson) => {
    (groups[lesson.topic_name] ||= []).push(lesson);
    return groups;
  }, {});
}

function updateXp(value) {
  state.localProgress.xp = Number(value || 0);
  saveJson(LOCAL_PROGRESS_KEY, state.localProgress);
}

function currentXp() {
  return Number(state.profile?.xp ?? state.localProgress.xp ?? 0);
}

function setMode(title, detail) {
  els.modePill.textContent = title;
  els.apiPill.textContent = detail;
  els.modePill.className = `pill ${state.apiAvailable ? "pill-online" : "pill-offline"}`;
}

function setStatus(message) {
  els.authMessage.textContent = message;
}

function byId(id) {
  return document.getElementById(id);
}

function loadJson(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key) || "") || fallback;
  } catch {
    return fallback;
  }
}

function saveJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}
