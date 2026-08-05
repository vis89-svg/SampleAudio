/* SampleAudio — Frontend Logic */
const audio = document.getElementById("audioElement");
const searchInput = document.getElementById("searchInput");
const resultsDiv = document.getElementById("results");
const tabsDiv = document.getElementById("tabs");
const artistView = document.getElementById("artistView");
const albumView = document.getElementById("albumView");
const playerDiv = document.getElementById("player");

let currentTab = "songs";
let queue = [];
let queueIndex = -1;
let searchCache = {};

searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doSearch();
});

async function doSearch() {
    const q = searchInput.value.trim();
    if (!q) return;

    showLoading();

    if (searchCache[q]) {
        renderResults(searchCache[q]);
        return;
    }

    try {
        const resp = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=20`);
        const data = await resp.json();
        searchCache[q] = data;
        renderResults(data);
    } catch (err) {
        resultsDiv.innerHTML = `<div class="empty-state">Search failed: ${err.message}</div>`;
    }
}

function renderResults(data) {
    tabsDiv.classList.remove("hidden");
    artistView.classList.add("hidden");
    albumView.classList.add("hidden");
    resultsDiv.classList.remove("hidden");

    if (currentTab === "songs") renderSongs(data.songs || []);
    else if (currentTab === "artists") renderArtists(data.artists || []);
    else if (currentTab === "albums") renderAlbums(data.albums || []);
}

function renderSongs(songs) {
    if (!songs.length) {
        resultsDiv.innerHTML = `<div class="empty-state">No songs found</div>`;
        return;
    }

    queue = songs;
    resultsDiv.innerHTML = songs.map((s, i) => `
        <div class="song-row" onclick="playSong(${i})">
            <img src="/api/thumbnail/${s.id}" alt="" loading="lazy" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22/>'">
            <div class="info">
                <div class="title">${esc(s.title)}${s.isExplicit ? '<span class="explicit-badge">E</span>' : ''}</div>
                <div class="subtitle">${esc(s.artist)}${s.album ? ' &middot; ' + esc(s.album) : ''}</div>
            </div>
            <div class="duration">${s.duration || ''}</div>
        </div>
    `).join("");
}

function renderArtists(artists) {
    if (!artists.length) {
        resultsDiv.innerHTML = `<div class="empty-state">No artists found</div>`;
        return;
    }
    resultsDiv.innerHTML = artists.map(a => `
        <div class="artist-card" onclick="openArtist('${a.id}')">
            <img src="/api/thumbnail/${a.id}" alt="" loading="lazy" onerror="this.style.background='#333'">
            <div class="title">${esc(a.name)}</div>
        </div>
    `).join("");
}

function renderAlbums(albums) {
    if (!albums.length) {
        resultsDiv.innerHTML = `<div class="empty-state">No albums found</div>`;
        return;
    }
    resultsDiv.innerHTML = albums.map(a => `
        <div class="album-card" onclick="openAlbum('${a.id}')">
            <img src="/api/thumbnail/${a.id}" alt="" loading="lazy" onerror="this.style.background='#333'">
            <div class="title">${esc(a.title)}</div>
            <div class="artist-name">${esc(a.artist)}${a.year ? ' &middot; ' + a.year : ''}</div>
        </div>
    `).join("");
}

function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tab));
    const cached = searchCache[searchInput.value.trim()];
    if (cached) renderResults(cached);
}

async function openArtist(browseId) {
    showLoading();
    tabsDiv.classList.add("hidden");
    resultsDiv.classList.add("hidden");
    albumView.classList.add("hidden");
    artistView.classList.remove("hidden");

    try {
        const resp = await fetch(`/api/artist/${browseId}`);
        const data = await resp.json();

        queue = data.top_songs || [];

        artistView.innerHTML = `
            <button class="back-btn" onclick="backToResults()">&larr; Back</button>
            <div class="artist-header">
                <img src="/api/thumbnail/${browseId}" alt="" onerror="this.style.background='#333'">
                <div>
                    <h2>${esc(data.name)}</h2>
                </div>
            </div>
            <div class="section-title">Top Songs</div>
            ${queue.map((s, i) => `
                <div class="song-row" onclick="playSong(${i})">
                    <img src="/api/thumbnail/${s.id}" alt="" loading="lazy" onerror="this.style.background='#333'">
                    <div class="info">
                        <div class="title">${esc(s.title)}</div>
                        <div class="subtitle">${esc(s.artist)}</div>
                    </div>
                    <div class="duration">${s.duration || ''}</div>
                </div>
            `).join("")}
            ${data.albums && data.albums.length ? `
                <div class="section-title" style="margin-top:24px">Albums</div>
                <div class="results">
                    ${data.albums.map(a => `
                        <div class="album-card" onclick="openAlbum('${a.id}')">
                            <img src="/api/thumbnail/${a.id}" alt="" loading="lazy" onerror="this.style.background='#333'">
                            <div class="title">${esc(a.title)}</div>
                            <div class="artist-name">${a.year || ''}</div>
                        </div>
                    `).join("")}
                </div>
            ` : ''}
        `;
    } catch (err) {
        artistView.innerHTML = `<div class="empty-state">Failed to load artist</div>`;
    }
}

async function openAlbum(browseId) {
    showLoading();
    tabsDiv.classList.add("hidden");
    resultsDiv.classList.add("hidden");
    artistView.classList.add("hidden");
    albumView.classList.remove("hidden");

    try {
        const resp = await fetch(`/api/album/${browseId}`);
        const data = await resp.json();

        queue = data.tracks || [];

        albumView.innerHTML = `
            <button class="back-btn" onclick="backToResults()">&larr; Back</button>
            <div class="artist-header">
                <img src="/api/thumbnail/${browseId}" alt="" style="border-radius:8px" onerror="this.style.background='#333'">
                <div>
                    <h2>${esc(data.title)}</h2>
                    <div style="color:#888;margin-top:4px">${esc(data.artist)}${data.year ? ' &middot; ' + data.year : ''}</div>
                </div>
            </div>
            <div class="section-title">Tracks</div>
            ${queue.map((t, i) => `
                <div class="song-row" onclick="playSong(${i})">
                    <img src="/api/thumbnail/${t.id}" alt="" loading="lazy" onerror="this.style.background='#333'">
                    <div class="info">
                        <div class="title">${t.number || ''}. ${esc(t.title)}</div>
                        <div class="subtitle">${esc(t.artist)}</div>
                    </div>
                    <div class="duration">${t.duration || ''}</div>
                </div>
            `).join("")}
        `;
    } catch (err) {
        albumView.innerHTML = `<div class="empty-state">Failed to load album</div>`;
    }
}

function backToResults() {
    artistView.classList.add("hidden");
    albumView.classList.add("hidden");
    resultsDiv.classList.remove("hidden");
    tabsDiv.classList.remove("hidden");
}

function playSong(index) {
    if (index < 0 || index >= queue.length) return;
    queueIndex = index;
    const song = queue[index];
    const quality = document.getElementById("qualitySelect").value;
    const clean = document.getElementById("cleanToggle").checked;

    document.getElementById("playerTitle").textContent = song.title;
    document.getElementById("playerArtist").textContent = "Loading...";
    document.getElementById("playerThumb").src = `/api/thumbnail/${song.id}`;
    playerDiv.classList.remove("hidden");
    document.getElementById("playPauseBtn").textContent = "Loading";
    hideCleanNote();

    audio.src = `/api/stream/${song.id}?quality=${quality}&clean=${clean}`;
    audio.load();

    if (clean) {
        fetch(`/api/sponsorblock/${song.id}/segments`)
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (data && data.total_skipped > 0) {
                    showCleanNote(`Clean audio: removed ${fmtTime(data.total_skipped)} of non-music content`);
                }
            })
            .catch(() => {});
    }

    audio.play().then(() => {
        document.getElementById("playPauseBtn").textContent = "Pause";
        document.getElementById("playerArtist").textContent = song.artist;
    }).catch(err => {
        console.error("Play failed:", err);
        document.getElementById("playPauseBtn").textContent = "Play";
        document.getElementById("playerArtist").textContent = "Failed to load - click Play to retry";
    });
}

function showCleanNote(msg) {
    let note = document.getElementById("cleanNote");
    if (!note) {
        note = document.createElement("div");
        note.id = "cleanNote";
        note.className = "clean-note";
        document.body.appendChild(note);
    }
    note.textContent = msg;
    note.classList.add("show");
}

function hideCleanNote() {
    const note = document.getElementById("cleanNote");
    if (note) note.classList.remove("show");
}

function togglePlay() {
    if (audio.paused) {
        audio.play().then(() => {
            document.getElementById("playPauseBtn").textContent = "Pause";
        }).catch(err => {
            console.error("Play failed:", err);
        });
    } else {
        audio.pause();
        document.getElementById("playPauseBtn").textContent = "Play";
    }
}

function prevTrack() {
    if (queueIndex > 0) playSong(queueIndex - 1);
}

function nextTrack() {
    if (queueIndex < queue.length - 1) playSong(queueIndex + 1);
}

audio.addEventListener("timeupdate", () => {
    if (audio.duration) {
        const pct = (audio.currentTime / audio.duration) * 100;
        document.getElementById("progressBar").value = pct;
        document.getElementById("currentTime").textContent = fmtTime(audio.currentTime);
        document.getElementById("totalTime").textContent = fmtTime(audio.duration);
    }
});

audio.addEventListener("loadedmetadata", () => {
    if (queueIndex >= 0 && queue[queueIndex]) {
        document.getElementById("playerArtist").textContent = queue[queueIndex].artist;
        document.getElementById("playPauseBtn").textContent = "Pause";
    }
});

audio.addEventListener("waiting", () => {
    document.getElementById("playPauseBtn").textContent = "Buffering";
});

audio.addEventListener("playing", () => {
    document.getElementById("playPauseBtn").textContent = "Pause";
});

audio.addEventListener("error", (e) => {
    console.error("Audio error:", e);
    document.getElementById("playPauseBtn").textContent = "Play";
    document.getElementById("playerArtist").textContent = "Error - click Play to retry";
});

audio.addEventListener("ended", () => {
    nextTrack();
});

function seekAudio(pct) {
    if (audio.duration) {
        audio.currentTime = (pct / 100) * audio.duration;
    }
}

function setVolume(pct) {
    audio.volume = pct / 100;
}

audio.volume = 0.8;

function fmtTime(s) {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
}

function esc(str) {
    const d = document.createElement("div");
    d.textContent = str || "";
    return d.innerHTML;
}

function showLoading() {
    resultsDiv.innerHTML = `<div class="loading">Searching...</div>`;
    resultsDiv.classList.remove("hidden");
    tabsDiv.classList.add("hidden");
    artistView.classList.add("hidden");
    albumView.classList.add("hidden");
}
