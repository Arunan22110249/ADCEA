(function () {
  const root = document.getElementById('root');
  
  function isLoggedIn() {
    return !!localStorage.getItem("adcea_token");
  }


  function getToken() {
    return localStorage.getItem('adcea_token');
  }

  function setToken(token) {
    if (token) localStorage.setItem('adcea_token', token);
  }

  function clearToken() {
    localStorage.removeItem('adcea_token');
  }

  function nav(active) {
  function link(href, label) {
    const isActive = active === href;
    return `<a href="#${href}" class="${isActive ? 'active' : ''}">${label}</a>`;
  }

  return `<div class="nav">
    <div style="font-weight:700; letter-spacing:.08em;">ADCEA</div>
    <div class="right">
      ${link('/', 'Home')}
      ${link('/analysis', 'Analysis')}
      ${link('/train', 'Train')}
      ${link('/models', 'Models')}
      ${link('/report', 'Report')}
      ${
        isLoggedIn()
          ? link('/me', 'Account')
          : link('/login', 'Login') + link('/register', 'Register')
      }
    </div>
  </div>`;
}


  async function safeJson(res) {
    const text = await res.text();
    try {
      return text ? JSON.parse(text) : {};
    } catch (e) {
      throw new Error(text || 'Unexpected response');
    }
  }

  function showError(msg) {
    const el = document.getElementById('error');
    if (el) {
      el.innerText = msg;
      el.style.display = 'block';
    } else {
      alert(msg);
    }
  }

  function home() {
    root.innerHTML = nav('/') + `
      <div class="container">
        <div class="card">
          <h1>Welcome to ADCEA</h1>
          <p>
            Upload a CSV dataset, quickly profile and clean it, engineer features,
            and train a baseline model – all from a single lightweight interface.
          </p>
          <div class="badge">FastAPI • scikit-learn • Chart.js</div>
        </div>
      </div>
    `;
  }

  function analysis() {
    root.innerHTML = nav('/analysis') + `
      <div class="container">
        <div class="card">
          <h2>Upload &amp; Profile</h2>
          <p>Drop a CSV file to see basic shape, dtypes, missing values, and a small preview.</p>
          <div class="field">
            <label>Select CSV</label>
            <input type="file" id="file" accept=".csv" />
          </div>
          <div id="error" class="error" style="display:none;"></div>
          <pre id="out"></pre>
        </div>
      </div>
    `;

    const input = document.getElementById('file');
    input.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append('file', file);
      try {
        const res = await fetch('/api/upload', { method: 'POST', body: fd });
        const j = await safeJson(res);
        document.getElementById('out').innerText = JSON.stringify(j, null, 2);
      } catch (err) {
        showError(err.message);
      }
    });
  }

  let epochChart = null;

  function renderEpochChart(history) {
    const ctx = document.getElementById('epoch').getContext('2d');
    if (epochChart && typeof epochChart.destroy === 'function') {
      epochChart.destroy();
    }
    const labels = history.map((e) => e.epoch);
    const values = history.map((e) => e.metric);
    epochChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Metric',
            data: values,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { title: { display: true, text: 'Epoch' } },
          y: { min: 0, max: 1, title: { display: true, text: 'Score' } },
        },
      },
    });
  }

  function train() {
    const token = getToken();
    root.innerHTML =
      nav('/train') +
      `
      <div class="container">
        <div class="card">
          <h2>Train Model</h2>
          <p>Upload a labeled CSV and specify the target column to train a baseline model.</p>
          <div class="grid-2">
            <div>
              <div class="field">
                <label>Dataset (CSV)</label>
                <input type="file" id="trainFile" accept=".csv" />
              </div>
              <div class="field">
                <label>Target Column</label>
                <input type="text" id="target" placeholder="target" />
              </div>
              <button id="startBtn"${token ? '' : ' disabled'}>${
        token ? 'Start Training' : 'Login required'
      }</button>
              <div id="status" class="status"></div>
              <div id="error" class="error" style="display:none;"></div>
            </div>
            <div>
              <canvas id="epoch" height="140"></canvas>
            </div>
          </div>
          <pre id="jobOut"></pre>
        </div>
      </div>
    `;

    let currentJobId = null;

    async function poll() {
      if (!currentJobId) return;
      try {
        const res = await fetch(`/api/train/status/${currentJobId}`, {
          headers: { Authorization: 'Bearer ' + getToken() },
        });
        const j = await safeJson(res);
        if (j.error) {
          showError(j.error);
          return;
        }
        document.getElementById('jobOut').innerText = JSON.stringify(j, null, 2);
        document.getElementById('status').innerText = 'Status: ' + j.status;
        if (j.epoch_history) {
          renderEpochChart(j.epoch_history);
        }
        if (j.status && (j.status === 'completed' || j.status === 'failed')) return;
        setTimeout(poll, 1500);
      } catch (err) {
        showError(err.message);
      }
    }

    const btn = document.getElementById('startBtn');
    btn.addEventListener('click', async () => {
      const file = document.getElementById('trainFile').files[0];
      const target = document.getElementById('target').value || 'target';
      if (!file) {
        showError('Please choose a CSV file.');
        return;
      }
      const fd = new FormData();
      fd.append('file', file);
      fd.append('target', target);
      btn.disabled = true;
      document.getElementById('status').innerText = 'Submitting job…';
      try {
        const res = await fetch('/api/train/start', {
          method: 'POST',
          body: fd,
          headers: { Authorization: 'Bearer ' + getToken() },
        });
        const j = await safeJson(res);
        if (j.error) {
          showError(j.error);
          btn.disabled = false;
          return;
        }
        currentJobId = j.job_id;
        document.getElementById('status').innerText = 'Job submitted. Tracking…';
        poll();
      } catch (err) {
        showError(err.message);
        btn.disabled = false;
      }
    });
  }

  async function models() {
    const token = getToken();
    if (!token) {
      root.innerHTML =
        nav('/models') +
        '<div class="container"><div class="card"><p>Please log in to view models.</p></div></div>';
      return;
    }

    root.innerHTML =
      nav('/models') +
      `
      <div class="container">
        <div class="card">
          <h2>Saved Models</h2>
          <p>Download trained models for offline use.</p>
          <div id="error" class="error" style="display:none;"></div>
          <ul id="modelsList"></ul>
        </div>
      </div>
    `;

    try {
      const res = await fetch('/api/models', {
        headers: { Authorization: 'Bearer ' + token },
      });
      const j = await safeJson(res);
      if (j.error) {
        showError(j.error);
        return;
      }
      const ul = document.getElementById('modelsList');
      if (!j.length) {
        ul.innerHTML = '<li style="color:var(--muted);">No models yet.</li>';
        return;
      }
      ul.innerHTML = j
  .map(
    (m) =>
      `<li><button class="secondary" onclick="downloadModel('${m.name}')">${m.name}</button></li>`
  )
  .join('');

    } catch (err) {
      showError(err.message);
    }
  }

  async function report() {
  root.innerHTML =
    nav('/report') +
    `
      <div class="container">
        <div class="card">
          <h2>Training Report</h2>
          <p>The latest completed training run will appear below.</p>
          <div id="status" class="status"></div>
          <div id="reportContainer" style="margin-top:1rem;"></div>
          <div id="error" class="error" style="display:none;"></div>
        </div>
      </div>
    `;

  const token = getToken();
  if (!token) {
    document.getElementById('status').innerText = 'Please log in to view reports.';
    return;
  }

  document.getElementById('status').innerText = 'Loading…';

  try {
    const res = await fetch('/api/report', {
      headers: { Authorization: 'Bearer ' + token }
    });

    if (res.status === 401) {
      document.getElementById('status').innerText = 'Unauthorized. Please log in again.';
      return;
    }

    const html = await res.text();
    document.getElementById('reportContainer').innerHTML = html;
    document.getElementById('status').innerText = '';
  } catch (err) {
    document.getElementById('status').innerText = 'Error loading report.';
    showError(err.message);
  }
}


  function authForm(kind) {
    const isLogin = kind === 'login';
    root.innerHTML =
      nav('/' + kind) +
      `
      <div class="container">
        <div class="card">
          <h2>${isLogin ? 'Login' : 'Create account'}</h2>
          <div class="grid-2">
            <div>
              <div class="field">
                <label>Email</label>
                <input type="email" id="email" placeholder="you@example.com" />
              </div>
              <div class="field">
                <label>Password</label>
                <input type="password" id="password" placeholder="••••••••" />
              </div>
              <button id="submit">${isLogin ? 'Login' : 'Register'}</button>
              <div id="error" class="error" style="display:none;"></div>
            </div>
            <div>
              <p>
                ${isLogin ? 'Use the account you created earlier.' : 'We only need a basic email/password to secure your jobs and models.'}
              </p>
            </div>
          </div>
        </div>
      </div>
    `;

    document.getElementById('submit').addEventListener('click', async () => {
      const email = document.getElementById('email').value.trim();
      const password = document.getElementById('password').value;
      if (!email || !password) {
        showError('Email and password are required.');
        return;
      }
      try {
        const res = await fetch(`/auth/${isLogin ? 'login' : 'register'}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        const j = await safeJson(res);
        if (j.detail || j.error) {
          showError(j.detail || j.error);
          return;
        }
        setToken(j.token);
        location.hash = '/';
      } catch (err) {
        showError(err.message);
      }
    });
  }

  async function account() {
    const token = getToken();
    if (!token) {
      root.innerHTML =
        nav('/me') +
        '<div class="container"><div class="card"><p>Please log in first.</p></div></div>';
      return;
    }

    root.innerHTML =
      nav('/me') +
      `
      <div class="container">
        <div class="card">
          <h2>Your Account</h2>
          <pre id="acct"></pre>
          <button id="logout" class="secondary">Logout</button>
          <div id="error" class="error" style="display:none;"></div>
        </div>
      </div>
    `;

    try {
      const res = await fetch('/auth/me', {
        headers: { Authorization: 'Bearer ' + token },
      });
      const j = await safeJson(res);
      if (j.detail || j.error) {
        showError(j.detail || j.error);
        return;
      }
      document.getElementById('acct').innerText = JSON.stringify(j, null, 2);
    } catch (err) {
      showError(err.message);
    }

    document.getElementById('logout').addEventListener('click', () => {
      clearToken();
      location.hash = '/';
    });
  }

window.downloadModel = async function (name) {
  const token = getToken();
  try {
    const res = await fetch(`/api/models/${encodeURIComponent(name)}/download`, {
      headers: { Authorization: 'Bearer ' + token }
    });

    if (res.status === 401) {
      alert("Unauthorized: Please log in.");
      return;
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();

    URL.revokeObjectURL(url);

  } catch (err) {
    alert("Download failed: " + err.message);
  }
};

  function router() {
    const h = location.hash.replace('#', '') || '/';
    if (h === '/' || h === '') home();
    else if (h.startsWith('/analysis')) analysis();
    else if (h.startsWith('/train')) train();
    else if (h.startsWith('/models')) models();
    else if (h.startsWith('/report')) report();
    else if (h.startsWith('/login')) authForm('login');
    else if (h.startsWith('/register')) authForm('register');
    else if (h.startsWith('/me')) account();
    else home();
  }

  window.addEventListener('hashchange', router);
  router();
})();