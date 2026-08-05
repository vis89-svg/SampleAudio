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
let currentSong = null;
let queueIndex = -1;
let searchCache = {};
let recommendations = [];
let upNextOpen = false;

/* === Sleep Timer === */
let sleepTimerTimeout = null;
let sleepTimerEnd = null;
let sleepTimerInterval = null;

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
            <img src="${s.thumbnail || ''}" alt="" loading="lazy" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22/>'">
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
            <img src="${a.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
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
            <img src="${a.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
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
                <img src="${data.thumbnail || ''}" alt="" onerror="this.style.background='#333'">
                <div>
                    <h2>${esc(data.name)}</h2>
                </div>
            </div>
            <div class="section-title">Top Songs</div>
            ${queue.map((s, i) => `
                <div class="song-row" onclick="playSong(${i})">
                    <img src="${s.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
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
                            <img src="${a.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
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
                <img src="${data.thumbnail || ''}" alt="" style="border-radius:8px" onerror="this.style.background='#333'">
                <div>
                    <h2>${esc(data.title)}</h2>
                    <div style="color:#888;margin-top:4px">${esc(data.artist)}${data.year ? ' &middot; ' + data.year : ''}</div>
                </div>
            </div>
            <div class="section-title">Tracks</div>
            ${queue.map((t, i) => `
                <div class="song-row" onclick="playSong(${i})">
                    <img src="${t.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
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
    currentSong = song;
    const quality = document.getElementById("qualitySelect").value;
    const clean = document.getElementById("cleanToggle").checked;

    document.getElementById("playerTitle").textContent = song.title;
    document.getElementById("playerArtist").textContent = song.artist || "Loading...";
    document.getElementById("playerThumb").src = song.thumbnail || '';
    document.getElementById("playerAlbumName").textContent = song.album || '';
    document.getElementById("playerAlbumName").style.pointerEvents = song.album_id ? "cursor" : "default";
    playerDiv.classList.remove("hidden");
    document.getElementById("playPauseBtn").classList.add("buffering");
    hideCleanNote();
    closeKebabMenu();

    audio.src = `/api/stream/${song.id}?quality=${quality}&clean=${clean}`;
    audio.load();

    if (quality === "saavn") {
        showCleanNote(`JioSaavn 320kbps - clean audio, no chatter`);
    } else if (clean) {
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
        updatePlayIcon();
        document.getElementById("playerArtist").textContent = song.artist;
    }).catch(err => {
        console.error("Play failed:", err);
        updatePlayIcon();
        document.getElementById("playerArtist").textContent = "Failed to load - click Play to retry";
    });

    fetchRecommendations(song.id);
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

function updatePlayIcon() {
    const playIcon = document.getElementById("playIcon");
    const pauseIcon = document.getElementById("pauseIcon");
    const npPlayIcon = document.getElementById("npPlayIcon");
    const npPauseIcon = document.getElementById("npPauseIcon");
    if (playIcon && pauseIcon) {
        if (audio.paused) {
            playIcon.classList.remove("hidden");
            pauseIcon.classList.add("hidden");
        } else {
            playIcon.classList.add("hidden");
            pauseIcon.classList.remove("hidden");
        }
    }
    if (npPlayIcon && npPauseIcon) {
        if (audio.paused) {
            npPlayIcon.classList.remove("hidden");
            npPauseIcon.classList.add("hidden");
        } else {
            npPlayIcon.classList.add("hidden");
            npPauseIcon.classList.remove("hidden");
        }
    }
}

function togglePlay() {
    if (audio.paused) {
        audio.play().then(() => {
            updatePlayIcon();
        }).catch(err => {
            console.error("Play failed:", err);
        });
    } else {
        audio.pause();
        updatePlayIcon();
    }
}

function prevTrack() {
    if (queueIndex > 0) playSong(queueIndex - 1);
}

function nextTrack() {
    if (queueIndex < queue.length - 1) {
        playSong(queueIndex + 1);
    } else if (recommendations.length > 0) {
        playRecommendation(0);
    }
}

async function fetchRecommendations(videoId) {
    if (!videoId) return;
    try {
        const resp = await fetch(`/api/recommendations?videoId=${encodeURIComponent(videoId)}&limit=25`);
        const data = await resp.json();
        recommendations = (data.tracks || []).filter(t => t.id !== currentSong?.id);
        if (upNextOpen) renderUpNext();
    } catch (err) {
        console.error("Recommendations failed:", err);
        recommendations = [];
    }
}

function renderUpNext() {
    const list = document.getElementById("upNextList");
    if (!recommendations.length) {
        list.innerHTML = `<div class="empty-state">No recommendations</div>`;
        return;
    }
    list.innerHTML = recommendations.map((s, i) => `
        <div class="song-row" onclick="playRecommendation(${i})">
            <img src="${s.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
            <div class="info">
                <div class="title">${esc(s.title)}${s.isExplicit ? '<span class="explicit-badge">E</span>' : ''}</div>
                <div class="subtitle">${esc(s.artist)}${s.album ? ' &middot; ' + esc(s.album) : ''}</div>
            </div>
            <div class="duration">${s.duration || ''}</div>
        </div>
    `).join("");
}

function playRecommendation(index) {
    if (index < 0 || index >= recommendations.length) return;
    const song = recommendations[index];
    const quality = document.getElementById("qualitySelect").value;
    const clean = document.getElementById("cleanToggle").checked;

    queue = recommendations;
    queueIndex = index;
    currentSong = song;

    document.getElementById("playerTitle").textContent = song.title;
    document.getElementById("playerArtist").textContent = song.artist || "Loading...";
    document.getElementById("playerThumb").src = song.thumbnail || '';
    document.getElementById("playerAlbumName").textContent = song.album || '';
    document.getElementById("playerAlbumName").style.pointerEvents = song.album_id ? "cursor" : "default";
    playerDiv.classList.remove("hidden");
    document.getElementById("playPauseBtn").classList.add("buffering");
    hideCleanNote();
    closeKebabMenu();

    audio.src = `/api/stream/${song.id}?quality=${quality}&clean=${clean}`;
    audio.load();

    if (quality === "saavn") {
        showCleanNote(`JioSaavn 320kbps - clean audio, no chatter`);
    } else if (clean) {
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
        updatePlayIcon();
        document.getElementById("playerArtist").textContent = song.artist;
    }).catch(err => {
        console.error("Play failed:", err);
        updatePlayIcon();
        document.getElementById("playerArtist").textContent = "Failed to load - click Play to retry";
    });

    fetchRecommendations(song.id);
}

function toggleUpNext() {
    upNextOpen = !upNextOpen;
    const panel = document.getElementById("upNextPanel");
    if (upNextOpen) {
        renderUpNext();
        panel.classList.remove("hidden");
    } else {
        panel.classList.add("hidden");
    }
}

function skipBackward() {
    audio.currentTime = Math.max(0, audio.currentTime - 10);
}

function skipForward() {
    audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 10);
}

/* === Kebab Menu === */
function toggleKebabMenu(event) {
    if (event) event.stopPropagation();
    const menu = document.getElementById("kebabMenu");
    menu.classList.toggle("hidden");
}

function closeKebabMenu() {
    const menu = document.getElementById("kebabMenu");
    if (menu) menu.classList.add("hidden");
}

document.addEventListener("click", (e) => {
    const menu = document.getElementById("kebabMenu");
    const btn = document.querySelector(".kebab-btn");
    if (menu && !menu.classList.contains("hidden")) {
        if (!menu.contains(e.target) && !btn.contains(e.target)) {
            menu.classList.add("hidden");
        }
    }
    const upNextPanel = document.getElementById("upNextPanel");
    const upNextBtn = document.getElementById("upNextBtn");
    if (upNextPanel && !upNextPanel.classList.contains("hidden")) {
        if (!upNextPanel.contains(e.target) && !upNextBtn.contains(e.target)) {
            toggleUpNext();
        }
    }
});

/* === View Artist / Album from player === */
function viewArtist() {
    closeKebabMenu();
    closeNowPlaying();
    if (currentSong && currentSong.artist_id) {
        openArtist(currentSong.artist_id);
    } else {
        showCleanNoInfo("No artist info available");
    }
}

function viewAlbum() {
    closeKebabMenu();
    closeNowPlaying();
    if (currentSong && currentSong.album_id) {
        openAlbum(currentSong.album_id);
    } else {
        showCleanNoInfo("No album info available");
    }
}

function showCleanNoInfo(msg) {
    let note = document.getElementById("cleanNote");
    if (!note) {
        note = document.createElement("div");
        note.id = "cleanNote";
        note.className = "clean-note";
        document.body.appendChild(note);
    }
    note.textContent = msg;
    note.classList.add("show");
    setTimeout(() => note.classList.remove("show"), 2000);
}

/* === Now Playing Overlay === */
function openNowPlaying() {
    closeKebabMenu();
    if (!currentSong) return;
    const overlay = document.getElementById("nowPlayingOverlay");
    document.getElementById("npThumb").src = currentSong.thumbnail || '';
    document.getElementById("npTitle").textContent = currentSong.title || '';
    document.getElementById("npArtist").textContent = currentSong.artist || '';
    document.getElementById("npAlbum").textContent = currentSong.album || '';
    document.getElementById("npArtist").style.pointerEvents = currentSong.artist_id ? "cursor" : "default";
    document.getElementById("npAlbum").style.pointerEvents = currentSong.album_id ? "cursor" : "default";
    overlay.classList.remove("hidden");
}

function closeNowPlaying() {
    const overlay = document.getElementById("nowPlayingOverlay");
    if (overlay) overlay.classList.add("hidden");
}

document.getElementById("playerAlbumName").addEventListener("click", () => {
    if (currentSong && currentSong.album_id) {
        openNowPlaying();
    }
});

document.getElementById("npArtist").addEventListener("click", () => {
    if (currentSong && currentSong.artist_id) {
        viewArtist();
    }
});

document.getElementById("npAlbum").addEventListener("click", () => {
    if (currentSong && currentSong.album_id) {
        viewAlbum();
    }
});

/* === Sleep Timer === */
function showSleepTimerMenu() {
    closeKebabMenu();
    const menu = document.getElementById("sleepTimerMenu");
    menu.classList.toggle("hidden");
}

function startSleepTimer(minutes) {
    cancelSleepTimer();
    sleepTimerEnd = Date.now() + minutes * 60 * 1000;
    sleepTimerTimeout = setTimeout(() => {
        audio.pause();
        cancelSleepTimer();
        showCleanNoInfo("Sleep timer ended");
    }, minutes * 60 * 1000);

    updateSleepBadge();
    sleepTimerInterval = setInterval(updateSleepBadge, 1000);
    document.getElementById("sleepTimerMenu").classList.add("hidden");
    showCleanNoInfo(`Sleep timer set for ${minutes} min`);
}

function cancelSleepTimer() {
    if (sleepTimerTimeout) {
        clearTimeout(sleepTimerTimeout);
        sleepTimerTimeout = null;
    }
    if (sleepTimerInterval) {
        clearInterval(sleepTimerInterval);
        sleepTimerInterval = null;
    }
    sleepTimerEnd = null;
    const badge = document.getElementById("sleepBadge");
    if (badge) badge.classList.add("hidden");
}

function updateSleepBadge() {
    if (!sleepTimerEnd) return;
    const remaining = Math.max(0, sleepTimerEnd - Date.now());
    const badge = document.getElementById("sleepBadge");
    if (remaining <= 0) {
        cancelSleepTimer();
        return;
    }
    const m = Math.floor(remaining / 60000);
    const s = Math.floor((remaining % 60000) / 1000);
    badge.textContent = `${m}:${s.toString().padStart(2, "0")}`;
    badge.classList.remove("hidden");
}

/* === Audio Events === */
audio.addEventListener("timeupdate", () => {
    if (audio.duration) {
        const pct = (audio.currentTime / audio.duration) * 100;
        document.getElementById("progressBar").value = pct;
        document.getElementById("currentTime").textContent = fmtTime(audio.currentTime);
        document.getElementById("totalTime").textContent = fmtTime(audio.duration);
        const npBar = document.getElementById("npProgressBar");
        const npCur = document.getElementById("npCurrentTime");
        const npTot = document.getElementById("npTotalTime");
        if (npBar) npBar.value = pct;
        if (npCur) npCur.textContent = fmtTime(audio.currentTime);
        if (npTot) npTot.textContent = fmtTime(audio.duration);
    }
});

audio.addEventListener("loadedmetadata", () => {
    if (queueIndex >= 0 && queue[queueIndex]) {
        document.getElementById("playerArtist").textContent = queue[queueIndex].artist;
        updatePlayIcon();
    }
});

audio.addEventListener("waiting", () => {
    const btn = document.getElementById("playPauseBtn");
    if (btn) btn.classList.add("buffering");
});

audio.addEventListener("playing", () => {
    const btn = document.getElementById("playPauseBtn");
    if (btn) btn.classList.remove("buffering");
    updatePlayIcon();
});

audio.addEventListener("error", (e) => {
    console.error("Audio error:", e);
    updatePlayIcon();
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

document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    if (!document.getElementById("nowPlayingOverlay").classList.contains("hidden")) {
        if (e.key === "Escape") closeNowPlaying();
        return;
    }
    switch (e.key) {
        case " ":
            e.preventDefault();
            togglePlay();
            break;
        case "ArrowLeft":
            e.preventDefault();
            skipBackward();
            break;
        case "ArrowRight":
            e.preventDefault();
            skipForward();
            break;
        case "ArrowUp":
            e.preventDefault();
            audio.volume = Math.min(1, audio.volume + 0.05);
            document.getElementById("volumeBar").value = audio.volume * 100;
            break;
        case "ArrowDown":
            e.preventDefault();
            audio.volume = Math.max(0, audio.volume - 0.05);
            document.getElementById("volumeBar").value = audio.volume * 100;
            break;
    }
});
