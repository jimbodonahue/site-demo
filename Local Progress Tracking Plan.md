### Local Progress Tracking Plan

  Goal: Enable users to keep track of their exercise progress on their own device without
  requiring a login. Provide an optional Download button to export the data as a file for
  users who prefer not to store it in the browser.
  ──────
  #### 1. Data Model (client‑side)
   Field           | Type               | Description
  -----------------|--------------------|-------------------------------------------------
   exercise_id     | string             | Unique identifier of the exercise (e.g., Django model PK).
   attempt_id      | string             | UUID of the current attempt (generated on page   load).
   completed_cells | array of numbers   | Indexes of cells the user has run successfully.
   last_saved      | ISO‑8601 timestamp | When the data was last persisted.
   progress_state  | object             | Any extra state the backend already returns (e.g., data preview).

  All data will be stored in localStorage under a single key, e.g.:

    const STORAGE_KEY = 'exerciseProgress';
    
    const progress = {
      exercise_id: '{{ exercise.id }}',
      attempt_id: '{{ attempt.id }}',
      completed_cells: [],          // updated when a cell runs without error
      last_saved: new Date().toISOString(),
      progress_state: {}           // optional extra server state
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
    
  Why localStorage?

  • Persisted across page reloads and browser sessions.
  • No server round‑trip, easy to read/write from JavaScript.
  • Limited to ~5‑10 MiB per origin, more than enough for the tiny JSON payloads we need.
  ──────
  #### 2. Automatic Save Hook
  Add a tiny helper that updates localStorage after every successful notebook run (or
  after any progress‑changing action).
    function saveProgress() {
      const data = {
        exercise_id: EXERCISE_ID,
        attempt_id: ATTEMPT_ID,
        completed_cells: completedCells,
        last_saved: new Date().toISOString(),
        progress_state: currentDataState,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    }
    
  Call saveProgress():

  • Inside runNotebook() after processing the response.
  • After resetData() (clears completed_cells).
  • Optionally after feature‑choice selections.
  ──────
  #### 3. Load on Page Init
  When the page loads, try to read the stored progress. If it matches the current
  exercise_id & attempt_id, restore state.
    function loadProgress() {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      if (data.exercise_id !== EXERCISE_ID) return; // another exercise
      // optionally validate attempt_id; if mismatched we start fresh
      completedCells = data.completed_cells || [];
      currentDataState = data.progress_state || initialData;
    }
    
  Invoke loadProgress() before renderNotebook() so the UI reflects previously completed
  cells.
  ──────
  #### 4. “Download” Button (export as JSON file)

  Add a button next to the toolbar that lets users download the stored JSON. This
  satisfies users who prefer a file on disk rather than browser storage.

  HTML (toolbar area):

    <button id="download-progress-button"
            class="rounded-full bg-emerald-600 px-5 py-3 text-sm font-semibold text-white
  transition hover:bg-emerald-500">
      Download Progress
    </button>
    
  JS handler:

    document.getElementById('download-progress-button')
            .addEventListener('click', () => {
      const data = localStorage.getItem(STORAGE_KEY) || '{}';
      const blob = new Blob([data], {type: 'application/json'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `exercise-${EXERCISE_ID}-progress.json`;
      a.click();
      URL.revokeObjectURL(url);
    });
    
  The file is self‑contained JSON and can be re‑imported later if needed (future
  extension).
  ──────
  #### 5. UI Integration Summary (what to add to exercise_detail.html)

    <div class="flex flex-wrap gap-3">
      <button id="reset-data-button" ...>Reset Data</button>
      <button id="run-notebook-button" ...>Run Notebook</button>
      <button id="add-cell-button" ...>Add Cell</button>
      <button id="download-progress-button" ...>Download Progress</button>
    </div>

  No CSS changes needed – the existing Tailwind utility classes already style buttons
  nicely.
  ──────
  #### 6. Security & Privacy Considerations

  • Local only: Data never leaves the user's device unless they explicitly click
  “Download”.
  • No personal identifiers: Only exercise and attempt IDs are stored – no email, name, or
  auth tokens.
  • Clear UI: The download button makes it obvious that a file will be saved; users can
  delete it anytime.
  ──────
  #### 7. Optional Future Enhancements (out of scope for now)

   Feature                                                                      | Benefit
  ------------------------------------------------------------------------------|---------
   Import button – let users re‑upload a previously downloaded JSON to resume   |
   progress on a different device.                                              |
   Encryption – encrypt the JSON with a passphrase stored only in memory (for   |
   privacy‑concerned users).                                                    |
   Auto‑expiry – purge stale progress after a configurable period (e.g., 30     |
   days).                                                                       |
  ──────
  ### Next Steps for Implementation

  1. Add the “Download Progress” button in the toolbar HTML (see snippet above).
  2. Insert the saveProgress & loadProgress helper functions into the existing script
  block, wiring them into runNotebook, resetData, and the page init flow.
  3. Update the runNotebook success path to push the current cell index into
  completedCells (e.g., after each successful cell run).
  4. Test locally by running a notebook, reloading the page, and confirming the UI
  restores the completed cells.
  5. Click the “Download Progress” button to verify a JSON file is produced and contains
  the expected structure.

  ## Anonymous, Secure User Identifier – How to Add It
  ### 1. What the identifier looks like

   Property    | Value
  -------------|--------------------------------------------------------------------------
   Length      | ≥ 128 bits (16 bytes)
   Encoding    | URL‑safe Base64 (A‑Z a‑z 0‑9 _ -)
   Entropy     | Cryptographically random (generated with the Web Crypto API)
   Collisions  | Negligible – probability ≈ 1 / 2⁶⁴ for millions of users
   Persistence | Stored in localStorage (or an HttpOnly cookie if you prefer server‑side handling)
   Resettable  | User can delete it via a “Reset ID” button – a new ID will be generated    | automatically

  A typical example:

    J3X_9v7U3K7y9aBdZsBccg
    
  ### 2. Generation (client‑side)

  Add a tiny helper script once (e.g. at the bottom of
  templates/exercises/exercise_detail.html after the existing IIFE).

    <script>
    /* ---------- 1⃣ Generate / retrieve anon‑ID ---------- */
    const ANON_ID_KEY = 'anonUserId';
    
    function getAnonId() {
      // 1⃣ Try to read an existing ID
      let id = localStorage.getItem(ANON_ID_KEY);
      if (id) return id;
    
      // 2⃣ If none, create a fresh 128‑bit random value
      const bytes = new Uint8Array(16);
      crypto.getRandomValues(bytes);                     // cryptographically secure
      // Convert to URL‑safe Base64 (no padding, replace +/ with -_)
      id = btoa(String.fromCharCode(...bytes))
              .replace(/\+/g, '-')
              .replace(/\//g, '_')
              .replace(/=+$/, '');
      localStorage.setItem(ANON_ID_KEY, id);
      return id;
    }
    
    /* expose globally for the forum component */
    window.ANON_USER_ID = getAnonId();
    </script>
    
  Why the Web Crypto API?
  It works only over HTTPS (or localhost) and guarantees true randomness, making the ID
  hard to guess or brute‑force.

  ### 3. Making the ID available to the forum

  Assuming the forum posts are submitted via a standard <form> (or an AJAX call), you can:

  1. Add a hidden field that the server reads:
    <input type="hidden" name="anon_user_id" id="anon-user-id-field">
    
  2. Populate it on page load (right after getAnonId() runs):
    document.getElementById('anon-user-id-field').value = window.ANON_USER_ID;
    
  3. Or include it as a request header for AJAX posts:
    fetch('/forum/post/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Anon-User-Id': window.ANON_USER_ID
        },
        body: JSON.stringify(payload)
    });
    

  The server should treat this value as a pseudonym only – it never ties back to personal
  info.

  ### 4. UI helpers (optional but useful)

   Feature                                   | Code snippet        | Placement
  -------------------------------------------|---------------------|----------------------
   Display ID (so users can quote it)        | <span id="display-  | Near the forum “new
                                             | anon-id"            | post” button
                                             | class="text-sm      |
                                             | text-slate-         |
                                             | 500"></span>        |
   Copy‑to‑clipboard button                  | ```html             |
   <button id="copy-anon-id"                 |                     |
   class="rounded-full bg-slate-200 px-3 py- |                     |
   1 text-xs hover:bg-slate-300">            |                     |
   Copy ID                                   |                     |
                                             |                     |

    | **Reset ID** (if user wants a fresh pseudonym) | ```html
    <button id="reset-anon-id"
            class="rounded-full bg-rose-600 px-3 py-1 text-xs text-white hover:bg-rose-
  500">
      Reset ID
    </button>
    ``` | Same container |
    
    **JS for the helpers (add after the generation code):**
    
    ```js
    // Show the current ID
    document.getElementById('display-anon-id').textContent = window.ANON_USER_ID;

    // Copy to clipboard
    document.getElementById('copy-anon-id')
            .addEventListener('click', () => navigator.clipboard.writeText(window.
  ANON_USER_ID));

    // Reset (creates a new ID and refreshes the UI)
    document.getElementById('reset-anon-id')
            .addEventListener('click', () => {
                localStorage.removeItem(ANON_ID_KEY);
                window.ANON_USER_ID = getAnonId();               // regenerate
                document.getElementById('display-anon-id').textContent = window.
  ANON_USER_ID;
                document.getElementById('anon-user-id-field').value = window.ANON_USER_ID;
            });

  ### 5. Server‑side sanity checks (minimal)

  When the forum receives anon_user_id:

    import re
    ANON_ID_REGEX = re.compile(r'^[A-Za-z0-9_-]{22}$')   # 16 bytes → 22 chars Base64URL

    def is_valid_anon_id(value: str) -> bool:
        return bool(ANON_ID_REGEX.fullmatch(value))

  If you later need to rate‑limit or detect abuse, you can store a hash of the ID (e.g.,
  SHA‑256) in your DB – the raw ID never leaves the client, preserving anonymity.

  ### 6. Summary of steps to integrate

  1. Add the generation helper (getAnonId) to the template (or a shared JS module).
  2. Insert a hidden input (anon_user_id) in every forum post form.
  3. Populate the hidden field with window.ANON_USER_ID on page load.
  4. (Optional) Add UI elements for displaying, copying, and resetting the ID.
  5. Server: validate the ID format; optionally store only a hash for moderation.

  With these eight lines of JS and a couple of HTML additions you now provide every
  visitor a unique, unguessable, anonymous identifier that can be safely used across the
  forum without ever requiring a login or storing personally‑identifiable data
