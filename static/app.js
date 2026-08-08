/* SampleAudio — Frontend Logic */
let audio = null;
let searchInput = null;
let resultsDiv = null;
let tabsDiv = null;
let artistView = null;
let albumView = null;
let playerDiv = null;

function cacheDomElements() {
    audio = document.getElementById("audioElement");
    searchInput = document.getElementById("searchInput");
    resultsDiv = document.getElementById("results");
    tabsDiv = document.getElementById("tabs");
    artistView = document.getElementById("artistView");
    albumView = document.getElementById("albumView");
    playerDiv = document.getElementById("player");
}

let listenersAttached = false;

function attachEventListeners() {
    if (listenersAttached) return;
    listenersAttached = true;
    if (searchInput) {
        searchInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") doSearch();
        });
    }
    if (audio) {
        audio.addEventListener("ended", () => {
            songCompleted = true;
            nextTrack();
        });

        audio.addEventListener("timeupdate", () => {
            const d = audioDuration();
            if (d > 0) {
                const pct = (audio.currentTime / d) * 100;
                if (!scrubbing) {
                    document.getElementById("progressBar").value = pct;
                }
                document.getElementById("currentTime").textContent = fmtTime(audio.currentTime);
                document.getElementById("totalTime").textContent = fmtTime(d);
                const npBar = document.getElementById("npProgressBar");
                const npCur = document.getElementById("npCurrentTime");
                const npTot = document.getElementById("npTotalTime");
                if (npBar && !scrubbing) npBar.value = pct;
                if (npCur) npCur.textContent = fmtTime(audio.currentTime);
                if (npTot) npTot.textContent = fmtTime(d);
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
            console.error("[DEBUG] Audio error:", e, "src:", audio.src, "error code:", audio.error ? audio.error.code : "none");
            updatePlayIcon();
            if (!audioErrorRetried && currentSong && currentSong.id) {
                audioErrorRetried = true;
                document.getElementById("playerArtist").textContent = "Still loading stream - retrying...";
                document.getElementById("playPauseBtn").classList.add("buffering");
                const q = document.getElementById("qualitySelect").value;
                const c = document.getElementById("cleanToggle").checked;
                setTimeout(() => {
                    audio.src = streamUrl(currentSong, q, c);
                    audio.load();
                    audio.play().catch(() => {
                        updatePlayIcon();
                        document.getElementById("playerArtist").textContent = "Error - click Play to retry";
                        if (queue.length > 0 || userQueue.length > 0 || recommendations.length > 0) {
                            setTimeout(nextTrack, 1000);
                        }
                    });
                }, 800);
                return;
            }
            document.getElementById("playerArtist").textContent = "Error - click Play to retry";
            if (queue.length > 0 || userQueue.length > 0 || recommendations.length > 0) {
                setTimeout(nextTrack, 1000);
            }
        });
    }
}

// Cache DOM elements immediately
cacheDomElements();

let currentTab = "songs";
let queue = [];
let currentSong = null;
let queueIndex = -1;
let queueSource = 'other';
let playedRecently = new Set();
let userQueue = [];
let searchCache = {};
let recommendations = [];
let upNextOpen = false;
let mainContext = "home";
let playHistory = [];
let historyNavigating = false;
let songCompleted = false;
let songStartTime = 0;
let homeFeedData = { recent: [], mixes: [], discovery: null, because: [], albums: [], artists: [], charts: [], hotHits: [], genres: [], genrePersonalized: false };
let homeFeedExpanded = new Set();
const ALBUM_LIMIT = 6;
const ARTIST_LIMIT = 6;

function pushToHistory(song) {
    if (!song || !song.id) return;
    if (playHistory.length && playHistory[playHistory.length - 1].id === song.id) return;
    playHistory.push(song);
    if (playHistory.length > 50) playHistory.shift();
}

/* === Auth State === */
const TOKEN_KEY = "sampleaudio_token";
const USER_KEY = "sampleaudio_user";
let currentUser = null;
let authToken = null;

function initAuth() {
    authToken = localStorage.getItem(TOKEN_KEY);
    const userStr = localStorage.getItem(USER_KEY);
    if (userStr) {
        try { currentUser = JSON.parse(userStr); } catch (e) { currentUser = null; }
    }
    updateAuthUI();
    if (currentUser && authToken) {
        loadLikes();
        startFeedAutoRefresh();
    }
}

function updateAuthUI() {
    const guestEl = document.getElementById("guestAuth");
    const userEl = document.getElementById("userAuth");
    if (!guestEl || !userEl) return;

    if (currentUser && authToken) {
        guestEl.classList.add("hidden");
        userEl.classList.remove("hidden");
        const initial = currentUser.username ? currentUser.username[0].toUpperCase() : "U";
        const iconEl = document.getElementById("userIcon");
        const nameEl = document.getElementById("userName");
        const dropNameEl = document.getElementById("dropdownUserName");
        if (iconEl) iconEl.textContent = initial;
        if (nameEl) nameEl.textContent = currentUser.username || "User";
        if (dropNameEl) dropNameEl.textContent = "@" + (currentUser.username || "user");
    } else {
        guestEl.classList.remove("hidden");
        userEl.classList.add("hidden");
    }
}

function toggleUserMenu() {
    const dropdown = document.getElementById("userDropdown");
    if (dropdown) dropdown.classList.toggle("hidden");
}

function logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    currentUser = null;
    authToken = null;
    updateAuthUI();
    toggleUserMenu();
}

async function authFetch(url, options = {}) {
    const headers = { ...options.headers };
    if (authToken) {
        headers["Authorization"] = "Bearer " + authToken;
    }
    const resp = await fetch(url, { ...options, headers });
    if (resp.status === 401 && authToken && !options.silent401) {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        currentUser = null;
        authToken = null;
        updateAuthUI();
        const dropdown = document.getElementById("userDropdown");
        if (dropdown) dropdown.classList.add("hidden");
        showCleanNoInfo("Session expired - please login again");
    }
    return resp;
}

function showProfilePage() {
    tabsDiv.classList.add("hidden");
    artistView.classList.add("hidden");
    albumView.classList.add("hidden");
    resultsDiv.classList.remove("hidden");
    resultsDiv.innerHTML = `<div class="loading">Loading your profile...</div>`;

    Promise.all([
        authFetch("/api/user/profile").then(r => r.ok ? r.json() : null),
        authFetch("/api/user/daily-mix").then(r => r.ok ? r.json() : {mixes: []}),
        authFetch("/api/user/suggestions").then(r => r.ok ? r.json() : {based_on_likes: [], top_artists: [], top_albums: []}),
    ]).then(([profile, mixes, suggestions]) => {
        if (!profile) {
            resultsDiv.innerHTML = `<div class="empty-state">Failed to load profile. <a href="#" onclick="logout(); window.location.href='/login.html'">Login again</a></div>`;
            return;
        }

        let html = `
            <div class="profile-header">
                <div class="profile-avatar">${(profile.username || "U")[0].toUpperCase()}</div>
                <div class="profile-info">
                    <h2>${esc(profile.username)}</h2>
                    <div class="profile-stats">
                        <span><strong>${profile.stats?.history_count || 0}</strong> Plays</span>
                        <span><strong>${profile.stats?.likes_count || 0}</strong> Likes</span>
                        <span><strong>${profile.stats?.followed_artists_count || 0}</strong> Artists</span>
                        <span><strong>${profile.stats?.followed_albums_count || 0}</strong> Albums</span>
                    </div>
                </div>
            </div>
        `;

        queueSource = 'other';
        if (mixes.mixes && mixes.mixes.length) {
            mixes.mixes.forEach((mix, mixIdx) => {
                if (!mix.tracks || !mix.tracks.length) return;
                const mixQueueStart = queue.length;
                queue = queue.concat(mix.tracks);
                html += `
                    <div class="profile-section">
                        <div class="profile-section-header">
                            <h3>&#127925; ${esc(mix.name)}</h3>
                            <span class="profile-section-subtitle">Based on: ${esc(mix.based_on.join(", "))}</span>
                            <button class="mix-play-btn" onclick="playSong(${mixQueueStart})">&#9654; Play Mix</button>
                        </div>
                        <div class="profile-section-tracks">
                            ${mix.tracks.slice(0, 5).map((t, i) => `
                                <div class="song-row" onclick="playSong(${mixQueueStart + i})">
                                    <img src="${t.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                                    <div class="info">
                                        <div class="title">${esc(t.title)}</div>
                                        <div class="subtitle">${esc(t.artist)}</div>
                                    </div>
                                    <div class="duration">${t.duration || ''}</div>
                                    ${kebabBtn(t)}
                                </div>
                            `).join("")}
                        </div>
                    </div>
                `;
            });
        }

        if (suggestions.based_on_likes && suggestions.based_on_likes.length) {
            const sugStart = queue.length;
            queue = queue.concat(suggestions.based_on_likes);
            html += `
                <div class="profile-section">
                    <div class="profile-section-header">
                        <h3>&#10084;&#65039; Because You Liked...</h3>
                    </div>
                    <div class="profile-section-tracks">
                        ${suggestions.based_on_likes.slice(0, 5).map((t, i) => `
                            <div class="song-row" onclick="playSong(${sugStart + i})">
                                <img src="${t.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                                <div class="info">
                                    <div class="title">${esc(t.title)}</div>
                                    <div class="subtitle">${esc(t.artist)}</div>
                                </div>
                                <div class="duration">${t.duration || ''}</div>
                                ${kebabBtn(t)}
                            </div>
                        `).join("")}
                    </div>
                </div>
            `;
        }

        if (suggestions.top_artists && suggestions.top_artists.length) {
            html += `
                <div class="profile-section">
                    <div class="profile-section-header">
                        <h3>&#127911; Your Top Artists</h3>
                    </div>
                    <div class="profile-section-grid">
                        ${suggestions.top_artists.slice(0, 6).map(a => `
                            <div class="mini-card" onclick="openArtist('${a.artist_id || ''}')" ${!a.artist_id ? 'style="opacity:0.5;cursor:default"' : ''}>
                                <div class="mini-card-icon">&#127908;</div>
                                <div class="mini-card-title">${esc(a.artist)}</div>
                                <div class="mini-card-sub">${a.play_count} plays</div>
                            </div>
                        `).join("")}
                    </div>
                </div>
            `;
        }

        if (suggestions.top_albums && suggestions.top_albums.length) {
            html += `
                <div class="profile-section">
                    <div class="profile-section-header">
                        <h3>&#128193; Suggested Albums</h3>
                        <span class="profile-section-subtitle">From your most played songs</span>
                    </div>
                    <div class="profile-section-grid">
                        ${suggestions.top_albums.slice(0, 6).map(a => `
                            <div class="mini-card" onclick="openAlbum('${a.album_id || ''}')" ${!a.album_id ? 'style="opacity:0.5;cursor:default"' : ''}>
                                <div class="mini-card-icon">&#128193;</div>
                                <div class="mini-card-title">${esc(a.album)}</div>
                                <div class="mini-card-sub">${esc(a.artist)} &middot; ${a.play_count} plays</div>
                            </div>
                        `).join("")}
                    </div>
                </div>
            `;
        }

        if (!mixes.mixes?.length && !suggestions.based_on_likes?.length && !suggestions.top_artists?.length) {
            html += `<div class="profile-empty">
                <h3>Start Listening!</h3>
                <p>Play some songs to get personalized Daily Mixes, artist recommendations, and album suggestions.</p>
                <a href="/" class="mix-play-btn" style="display:inline-block;text-decoration:none">&#128269; Search Songs</a>
            </div>`;
        }

        resultsDiv.innerHTML = html;
    }).catch(() => {
        resultsDiv.innerHTML = `<div class="empty-state">Failed to load profile. Please try again.</div>`;
    });
}

function viewProfile() {
    toggleUserMenu();
    if (!authToken) return showCleanNoInfo("Login required");
    showProfilePage();
}

function viewLikes() {
    toggleUserMenu();
    if (!authToken) return showCleanNoInfo("Login required");
    tabsDiv.classList.add("hidden");
    artistView.classList.add("hidden");
    albumView.classList.add("hidden");
    resultsDiv.classList.remove("hidden");
    resultsDiv.innerHTML = `<div class="loading">Loading your likes...</div>`;

    authFetch("/api/user/likes")
        .then(r => {
            if (!r.ok) throw new Error("Failed");
            return r.json();
        })
        .then(data => {
            const likes = data.likes || [];
            if (!likes.length) {
                resultsDiv.innerHTML = `<div class="empty-state">No liked songs yet. Click the heart on any song to save it here.</div>`;
                return;
            }
            queue = likes;
            queueSource = 'other';
            resultsDiv.innerHTML = `
                <div class="profile-section-header"><h3>&#10084;&#65039; Liked Songs (${likes.length})</h3></div>
                ${likes.map((s, i) => `
                    <div class="song-row" onclick="playSong(${i})">
                        <img src="${s.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                        <div class="info">
                            <div class="title">${esc(s.title || "Unknown")}</div>
                            <div class="subtitle">${esc(s.artist || "")}${s.album ? ' &middot; ' + esc(s.album) : ''}</div>
                        </div>
                        <div class="duration">${s.duration || ''}</div>
                        ${kebabBtn(s)}
                    </div>
                `).join("")}
            `;
        })
        .catch(() => {
            resultsDiv.innerHTML = `<div class="empty-state">Failed to load likes. Please log in again.</div>`;
        });
}

function viewHistory() {
    toggleUserMenu();
    if (!authToken) return showCleanNoInfo("Login required");
    tabsDiv.classList.add("hidden");
    artistView.classList.add("hidden");
    albumView.classList.add("hidden");
    resultsDiv.classList.remove("hidden");
    resultsDiv.innerHTML = `<div class="loading">Loading your history...</div>`;

    authFetch("/api/user/history?limit=50")
        .then(r => {
            if (!r.ok) throw new Error("Failed");
            return r.json();
        })
        .then(data => {
            const history = data.history || [];
            if (!history.length) {
                resultsDiv.innerHTML = `<div class="empty-state">No listening history yet. Play some songs to build your history.</div>`;
                return;
            }
            queue = history;
            queueSource = 'other';
            resultsDiv.innerHTML = `
                <div class="profile-section-header"><h3>&#128338; Recently Played (${history.length})</h3></div>
                ${history.map((s, i) => `
                    <div class="song-row" onclick="playSong(${i})">
                        <img src="${s.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                        <div class="info">
                            <div class="title">${esc(s.title || "Unknown")}</div>
                            <div class="subtitle">${esc(s.artist || "")}${s.album ? ' &middot; ' + esc(s.album) : ''}</div>
                        </div>
                        <div class="duration">${s.duration || ''}</div>
                        ${kebabBtn(s)}
                    </div>
                `).join("")}
            `;
        })
        .catch(() => {
            resultsDiv.innerHTML = `<div class="empty-state">Failed to load history. Please log in again.</div>`;
        });
}

function viewFollowedArtists() {
    toggleUserMenu();
    if (!authToken) return showCleanNoInfo("Login required");
    tabsDiv.classList.add("hidden");
    artistView.classList.add("hidden");
    albumView.classList.add("hidden");
    resultsDiv.classList.remove("hidden");
    resultsDiv.innerHTML = `<div class="loading">Loading followed artists...</div>`;

    authFetch("/api/user/followed-artists")
        .then(r => {
            if (!r.ok) throw new Error("Failed");
            return r.json();
        })
        .then(data => {
            const artists = data.artists || [];
            if (!artists.length) {
                resultsDiv.innerHTML = `<div class="empty-state">No followed artists yet. Visit an artist page and click "Follow" to add them here.</div>`;
                return;
            }
            resultsDiv.innerHTML = `
                <div class="profile-section-header"><h3>&#127908; Followed Artists (${artists.length})</h3></div>
                <div class="profile-section-grid">
                    ${artists.map(a => `
                        <div class="mini-card" onclick="openArtist('${a.artist_id}')">
                            <div class="mini-card-icon">&#127908;</div>
                            <div class="mini-card-title">${esc(a.artist_name)}</div>
                        </div>
                    `).join("")}
                </div>
            `;
        })
        .catch(() => {
            resultsDiv.innerHTML = `<div class="empty-state">Failed to load followed artists.</div>`;
        });
}

function connectYTMusic() {
    toggleUserMenu();
    if (!authToken) return showCleanNoInfo("Login required");
    showCleanNoInfo("OAuth setup coming soon — add oauth_config.json to enable");
}

/* === Sleep Timer === */
let sleepTimerTimeout = null;
let sleepTimerEnd = null;
let sleepTimerInterval = null;

async function doSearch() {
    const q = searchInput.value.trim();
    if (!q) return;

    showSearch();
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
    console.log('[DEBUG] renderSongs called, count:', songs.length);
    if (!songs.length) {
        resultsDiv.innerHTML = `<div class="empty-state">No songs found</div>`;
        return;
    }

    queue = songs;
    queueSource = 'other';
    console.log('[DEBUG] queue set, first song id:', songs[0].id);
    resultsDiv.innerHTML = songs.map((s, i) => `
        <div class="song-row" onclick="playSong(${i})">
            <img src="${s.thumbnail || ''}" alt="" loading="lazy" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22/>'">
            <div class="info">
                <div class="title">${esc(s.title)}${s.isExplicit ? '<span class="explicit-badge">E</span>' : ''}</div>
                <div class="subtitle">${esc(s.artist)}${s.album ? ' &middot; ' + esc(s.album) : ''}</div>
            </div>
            <div class="duration">${s.duration || ''}</div>
            ${kebabBtn(s)}
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

let artistData = null;
let artistSection = 'most';
let artistAllSongs = null;

function upsizeThumb(url) {
    if (!url) return '';
    return url.replace(/=w\d+-h\d+/, '=w800-h800');
}

function playCountBadge(song) {
    if (song && song.play_count > 0) {
        return `<span class="play-count">${fmtPlays(song.play_count)}</span>`;
    }
    return '';
}

function fmtPlays(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, '') + 'M plays';
    if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'K plays';
    return n + (n === 1 ? ' play' : ' plays');
}

function artistSongRows(songs, action) {
    return songs.map((s, i) => `
        <div class="song-row" onclick="${action}(${i})">
            <img src="${s.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
            <div class="info">
                <div class="title">${esc(s.title || '')}</div>
                <div class="subtitle">${esc(s.artist || '')}</div>
            </div>
            ${playCountBadge(s)}
            <div class="duration">${s.duration || ''}</div>
            ${kebabBtn(s)}
        </div>
    `).join("");
}

function albumGrid(albums) {
    return `<div class="results">${(albums || []).map(a => `
        <div class="album-card" onclick="openAlbum('${a.id}')">
            <img src="${a.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
            <div class="title">${esc(a.title || '')}</div>
            <div class="artist-name">${esc(a.year || '')}</div>
        </div>
    `).join("")}</div>`;
}

async function openArtist(browseId) {
    showLoading();
    const homeViewEl = document.getElementById("homeView");
    const searchViewEl = document.getElementById("searchView");
    if (homeViewEl) homeViewEl.classList.add("hidden");
    if (searchViewEl) searchViewEl.classList.remove("hidden");
    tabsDiv.classList.add("hidden");
    resultsDiv.classList.add("hidden");
    albumView.classList.add("hidden");
    artistView.classList.remove("hidden");

    try {
        const [resp, extraResp] = await Promise.all([
            authFetch(`/api/artist/${browseId}`),
            authFetch(`/api/artist/${browseId}/playlists`),
        ]);
        const data = await resp.json();
        const extras = extraResp.ok ? await extraResp.json() : {};

        artistData = data;
        artistData.playlists = extras;
        artistSection = 'most';
        artistAllSongs = null;

        queue = data.top_songs || [];
        queueSource = 'other';

        authFetch(`/api/artist/${browseId}/featuring`)
            .then(r => r.ok ? r.json() : {})
            .then(f => {
                if (artistData && artistData.id === browseId) {
                    artistData.featuring = f.tracks || [];
                    if (document.getElementById("artistFeaturing")) {
                        document.getElementById("artistFeaturing").innerHTML = featuringHtml();
                    }
                }
            })
            .catch(() => {});

        renderArtistView();
    } catch (err) {
        artistView.innerHTML = `<div class="empty-state">Failed to load artist</div>`;
    }
}

function renderArtistView() {
    if (!artistData) return;
    const d = artistData;
    const topSongs = d.top_songs || [];
    const monthly = d.monthly_listeners ? ` ${d.monthly_listeners} monthly listeners` : '';
    const bigThumb = upsizeThumb(d.thumbnail);

    let content = '';
    if (artistSection === 'most') {
        const shown = topSongs.slice(0, 8);
        content = `
            <div class="section-title">Most Played</div>
            ${artistSongRows(shown, 'playSong')}
            ${(d.total_songs && d.total_songs > shown.length) ? `<button class="see-more-btn" onclick="seeAllArtistSongs()">See More &darr;</button>` : ''}
        `;
    } else if (artistSection === 'recent') {
        const recent = (d.singles || []).concat(d.albums || [])
            .sort((x, y) => parseInt(y.year || 0, 10) - parseInt(x.year || 0, 10))
            .slice(0, 12);
        content = `<div class="section-title">Recently Released</div>${albumGrid(recent)}`;
    } else if (artistSection === 'albums') {
        content = `<div class="section-title">Albums</div>${albumGrid(d.albums || [])}`;
    } else if (artistSection === 'playlists') {
        const featured = (d.playlists && d.playlists.featured) || [];
        const byArtist = (d.playlists && d.playlists.by_artist) || [];
        content = `
            ${featured.length ? `
                <div class="section-title">Featured On</div>
                <div class="results">${featured.map(p => `
                    <div class="album-card" onclick="openArtistPlaylist('${p.id}')">
                        <img src="${p.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                        <div class="title">${esc(p.title || '')}</div>
                        <div class="artist-name">Playlist</div>
                    </div>
                `).join("")}</div>
            ` : ''}
            ${byArtist.length ? `
                <div class="section-title" style="margin-top:24px">Playlists by ${esc(d.name)}</div>
                <div class="results">${byArtist.map(p => `
                    <div class="album-card" onclick="openArtistPlaylist('${p.id}')">
                        <img src="${p.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                        <div class="title">${esc(p.title || '')}</div>
                        <div class="artist-name">Playlist</div>
                    </div>
                `).join("")}</div>
            ` : ''}
            ${(!featured.length && !byArtist.length) ? `<div class="empty-state">No playlists found</div>` : ''}
        `;
    }

    const related = (d.related || []).slice(0, 12);

    artistView.innerHTML = `
        <button class="back-btn" onclick="backToResults()">&larr; Back</button>
        <div class="artist-banner">
            <img class="artist-banner-bg" src="${bigThumb}" alt="" onerror="this.style.display='none'">
            <div class="artist-banner-overlay"></div>
            <div class="artist-banner-content">
                <img class="artist-banner-img" src="${d.thumbnail || ''}" alt="" onerror="this.style.background='#333'">
                <div class="artist-banner-text">
                    <div class="artist-banner-title">${esc(d.name)}</div>
                    ${monthly ? `<div class="artist-banner-sub">${monthly}</div>` : ''}
                    <div class="artist-banner-buttons">
                        ${topSongs.length ? `<button class="mix-play-btn" onclick="playSong(0)">&#9654; Play</button>` : ''}
                        <button class="artist-radio-btn" onclick="playArtistRadio()">&#9658; Radio</button>
                    </div>
                </div>
            </div>
        </div>
        <div class="artist-section-tabs">
            <button class="artist-section-tab ${artistSection === 'most' ? 'active' : ''}" onclick="artistTab('most')">Most Played</button>
            <button class="artist-section-tab ${artistSection === 'recent' ? 'active' : ''}" onclick="artistTab('recent')">Recently Released</button>
            <button class="artist-section-tab ${artistSection === 'albums' ? 'active' : ''}" onclick="artistTab('albums')">Albums</button>
            <button class="artist-section-tab ${artistSection === 'playlists' ? 'active' : ''}" onclick="artistTab('playlists')">Playlists</button>
        </div>
        <div id="artistSectionContent">${content}</div>
        <div id="artistFeaturing">${featuringHtml()}</div>
        ${related.length ? `
            <div class="section-title" style="margin-top:24px">Fans Also Like</div>
            <div class="results">${related.map(r => `
                <div class="artist-card" onclick="openArtist('${r.id}')">
                    <img src="${r.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                    <div class="title">${esc(r.name || '')}</div>
                    <div class="artist-name">${esc(r.subscribers || 'Artist')}</div>
                </div>
            `).join("")}</div>
        ` : ''}
    `;
}

function featuringHtml() {
    if (!artistData || !artistData.featuring || !artistData.featuring.length) return '';
    const d = artistData;
    const tracks = d.featuring;
    return `
        <div class="section-title" style="margin-top:24px">Songs Featuring ${esc(d.name)}</div>
        ${tracks.map((t, i) => `
            <div class="song-row" onclick="playFeaturingTrack(${i})">
                <img src="${t.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                <div class="info">
                    <div class="title">${esc(t.title || '')}</div>
                    <div class="subtitle">${esc(t.artist || '')}</div>
                </div>
                <div class="duration">${t.duration || ''}</div>
                ${kebabBtn(t)}
            </div>
        `).join("")}
    `;
}

function playFeaturingTrack(i) {
    if (!artistData || !artistData.featuring) return;
    queue = artistData.featuring;
    queueSource = 'other';
    playSong(i);
}

function artistTab(tab) {
    artistSection = tab;
    renderArtistView();
}

async function seeAllArtistSongs() {
    if (!artistData) return;
    if (!artistAllSongs) {
        const resp = await authFetch(`/api/artist/${artistData.id}/songs`);
        if (!resp.ok) return;
        const data = await resp.json();
        artistAllSongs = data.songs || [];
    }
    const songs = artistAllSongs;
    document.getElementById("artistSectionContent").innerHTML = `
        <button class="back-btn" style="margin-top:8px" onclick="artistTab('most')">&larr; Back</button>
        <div class="section-title">All Songs &middot; ${songs.length}</div>
        ${artistSongRows(songs, 'playArtistAllSong')}
    `;
}

function playArtistAllSong(i) {
    if (!artistAllSongs) return;
    queue = artistAllSongs;
    queueSource = 'other';
    playSong(i);
}

async function playArtistRadio() {
    if (!artistData) return;
    showCleanNoInfo("Starting artist radio...");
    try {
        const resp = await authFetch(`/api/artist/${artistData.id}/radio`);
        if (!resp.ok) return;
        const data = await resp.json();
        const tracks = data.tracks || [];
        if (!tracks.length) return;
        queue = tracks;
        queueSource = 'artist-radio';
        enqueueMixTracks(queue.slice(1));
        playSong(0);
    } catch (e) {
        showCleanNoInfo("Failed to start radio");
    }
}

async function openArtistPlaylist(playlistId, title) {
    try {
        const resp = await authFetch(`/api/playlist/${playlistId}`);
        if (!resp.ok) {
            artistView.innerHTML = `<div class="empty-state">Failed to load playlist</div>`;
            return;
        }
        const data = await resp.json();
        const tracks = data.tracks || [];
        const name = data.title || title || 'Playlist';
        queue = tracks;
        queueSource = 'other';
        artistView.innerHTML = `
            <button class="back-btn" onclick="renderArtistView()">&larr; Back</button>
            <div class="artist-header">
                <div>
                    <h2>${esc(name)}</h2>
                    <div style="color:#888;margin-top:4px">${tracks.length} songs</div>
                </div>
                <button class="mix-play-btn" onclick="playSong(0)" title="Play all">&#9654; Play</button>
            </div>
            <div class="section-title">Songs</div>
            ${tracks.map((t, i) => `
                <div class="song-row" onclick="playSong(${i})">
                    <img src="${t.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                    <div class="info">
                        <div class="title">${esc(t.title || '')}</div>
                        <div class="subtitle">${esc(t.artist || '')}</div>
                    </div>
                    <div class="duration">${t.duration || ''}</div>
                    ${kebabBtn(t)}
                </div>
            `).join("")}
        `;
    } catch (e) {
        artistView.innerHTML = `<div class="empty-state">Failed to load playlist</div>`;
    }
}

async function openAlbum(browseId) {
    showLoading();
    const homeViewEl = document.getElementById("homeView");
    const searchViewEl = document.getElementById("searchView");
    if (homeViewEl) homeViewEl.classList.add("hidden");
    if (searchViewEl) searchViewEl.classList.remove("hidden");
    tabsDiv.classList.add("hidden");
    resultsDiv.classList.add("hidden");
    artistView.classList.add("hidden");
    albumView.classList.remove("hidden");

    try {
        const resp = await fetch(`/api/album/${browseId}`);
        const data = await resp.json();

        queue = data.tracks || [];
        queueSource = 'album';

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
                    ${kebabBtn(t)}
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
    if (mainContext === "home") {
        showHome();
    } else {
        resultsDiv.classList.remove("hidden");
        tabsDiv.classList.remove("hidden");
    }
}

function streamUrl(song, quality, clean) {
    const p = new URLSearchParams();
    p.set("quality", quality);
    if (clean) p.set("clean", "true");
    if (song.title) p.set("title", song.title);
    if (song.artist) p.set("artist", song.artist);
    if (song.duration_seconds) p.set("dur", song.duration_seconds);
    return `/api/stream/${encodeURIComponent(song.id)}?${p.toString()}`;
}

function playSong(index) {
    console.log('[DEBUG] playSong called, index:', index, 'queue.length:', queue.length);
    if (index < 0 || index >= queue.length) {
        console.log('[DEBUG] playSong: index out of range');
        return;
    }
    if (currentSong && currentSong.id !== queue[index].id && !historyNavigating) {
        logPlayCompletion(currentSong, songCompleted, !songCompleted);
        pushToHistory(currentSong);
    }
    if (queueSource !== 'daily-mix' && queueSource !== 'discovery' && queueSource !== 'because-liked' && queueSource !== 'charts' && queueSource !== 'hot-hits' && queueSource !== 'genres' && queueSource !== 'artist-radio') {
        clearStaleQueueItems();
    }
    audioErrorRetried = false;
    queueIndex = index;
    const song = queue[index];
    console.log('[DEBUG] playSong song:', JSON.stringify(song));
    currentSong = song;
    songCompleted = false;
    songStartTime = Date.now();
    playedRecently.add(song.id);
    if (playedRecently.size > 5) playedRecently.delete([...playedRecently][0]);
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

    audio.src = streamUrl(song, quality, clean);
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
    logPlay(song);
    updateLikeButton();
}

function playNextSong(song) {
    if (userQueue.length >= 50) {
        showCleanNoInfo("Queue is full (50 songs max)");
        return;
    }
    userQueue.unshift(song);
    showCleanNoInfo("Added to play next (" + userQueue.length + " in queue)");
}

function removeFromQueue(index) {
    userQueue.splice(index, 1);
    if (upNextOpen) renderUpNext();
}

function clearQueue() {
    userQueue = [];
    if (upNextOpen) renderUpNext();
}

let currentMenuSong = null;

function kebabBtn(song) {
    const json = JSON.stringify(song).replace(/"/g, '&quot;');
    return `<button class="song-kebab-btn" data-song="${json}" onclick="event.stopPropagation(); showSongMenu(this)" title="More options">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="3" r="1.5"/><circle cx="8" cy="8" r="1.5"/><circle cx="8" cy="13" r="1.5"/></svg>
    </button>`;
}

function showSongMenu(btn) {
    closeSongMenu();
    const song = JSON.parse(btn.dataset.song);
    currentMenuSong = song;

    const rect = btn.getBoundingClientRect();
    const menu = document.createElement("div");
    menu.id = "songMenu";
    menu.className = "song-menu";
    menu.style.position = "fixed";
    menu.style.top = (rect.bottom + 4) + "px";
    menu.style.left = Math.min(rect.left - 120, window.innerWidth - 160) + "px";
    menu.style.zIndex = "300";
    menu.innerHTML = `
        <button onclick="playNextSong(currentMenuSong); closeSongMenu();">
            &#9658; Play Next
        </button>
    `;
    document.body.appendChild(menu);
}

function closeSongMenu() {
    const existing = document.getElementById("songMenu");
    if (existing) existing.remove();
    currentMenuSong = null;
}

function playSongDirect(song) {
    if (currentSong && currentSong.id !== song.id && !historyNavigating) {
        logPlayCompletion(currentSong, songCompleted, !songCompleted);
        pushToHistory(currentSong);
    }
    audioErrorRetried = false;
    currentSong = song;
    songCompleted = false;
    songStartTime = Date.now();
    if (userQueue.length > 0) {
        const qIdx = userQueue.findIndex(s => s.id === song.id);
        if (qIdx >= 0) {
            userQueue.splice(qIdx, 1);
            renderUpNext();
        }
    }
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

    audio.src = streamUrl(song, quality, clean);
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
    logPlay(song);
    updateLikeButton();
}

function logPlay(song, extras = {}) {
    if (!authToken || !song || !song.id) return;
    const durationPlayed = extras.duration_played || 0;
    const completed = extras.completed || false;
    const skipped = extras.skipped || false;
    const skipPosition = extras.skip_position || 0;
    authFetch("/api/user/history", {
        method: "POST",
        silent401: true,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            video_id: song.id,
            title: song.title || "",
            artist: song.artist || "",
            album: song.album || "",
            thumbnail: song.thumbnail || "",
            duration: song.duration || "",
            duration_seconds: song.duration_seconds || 0,
            artist_id: song.artist_id || "",
            album_id: song.album_id || "",
            duration_played: durationPlayed,
            completed: completed,
            skipped: skipped,
            skip_position: skipPosition,
        }),
    }).catch(() => {});
}

function logPlayCompletion(song, completed, skipped) {
    if (!song || !song.id) return;
    const durationPlayed = completed ? (song.duration_seconds || 0) : Math.floor(audio.currentTime || 0);
    const skipPosition = skipped ? Math.floor(audio.currentTime || 0) : 0;
    logPlay(song, { duration_played: durationPlayed, completed, skipped, skip_position: skipPosition });
}

let likedSongIds = new Set();

function loadLikes() {
    if (!authToken) return;
    authFetch("/api/user/likes")
        .then(r => r.ok ? r.json() : {likes: []})
        .then(data => {
            likedSongIds = new Set((data.likes || []).map(l => l.video_id));
            updateLikeButton();
        })
        .catch(() => {});
}

function toggleLike() {
    if (!authToken) return showCleanNoInfo("Login required to like songs");
    if (!currentSong || !currentSong.id) return;

    const isLiked = likedSongIds.has(currentSong.id);
    const method = isLiked ? "DELETE" : "POST";
    const url = isLiked ? `/api/user/like/${currentSong.id}` : "/api/user/like";

    authFetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: isLiked ? undefined : JSON.stringify({
            video_id: currentSong.id,
            title: currentSong.title || "",
            artist: currentSong.artist || "",
            album: currentSong.album || "",
            thumbnail: currentSong.thumbnail || "",
            duration: currentSong.duration || "",
            duration_seconds: currentSong.duration_seconds || 0,
            artist_id: currentSong.artist_id || "",
            album_id: currentSong.album_id || "",
        }),
    }).then(r => {
        if (r.ok) {
            if (isLiked) {
                likedSongIds.delete(currentSong.id);
                showCleanNoInfo("Removed from likes");
            } else {
                likedSongIds.add(currentSong.id);
                showCleanNoInfo("Added to likes");
            }
            updateLikeButton();
            refreshHomeFeedQuiet();
        } else if (r.status !== 401) {
            showCleanNoInfo("Failed to update like. Please try again.");
        }
    }).catch(() => {
        showCleanNoInfo("Failed to update like. Please try again.");
    });
}

function updateLikeButton() {
    const btn = document.getElementById("likeBtn");
    if (!btn) return;
    if (currentSong && likedSongIds.has(currentSong.id)) {
        btn.innerHTML = "&#10084;&#65039; Liked";
        btn.classList.add("liked");
    } else {
        btn.innerHTML = "&#9829; Like";
        btn.classList.remove("liked");
    }
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
    if (playHistory.length > 0) {
        const prev = playHistory.pop();
        historyNavigating = true;
        const qIdx = queue.findIndex(s => s.id === prev.id);
        if (qIdx >= 0) queueIndex = qIdx;
        playSongDirect(prev);
        historyNavigating = false;
        return;
    }
    if (queueIndex > 0) playSong(queueIndex - 1);
}

function nextTrack() {
    if (userQueue.length > 0) {
        const song = userQueue.shift();
        playedRecently.add(song.id);
        if (playedRecently.size > 5) playedRecently.delete([...playedRecently][0]);
        playSongDirect(song);
    } else if (queueSource === 'album') {
        if (queueIndex < queue.length - 1) {
            playSong(queueIndex + 1);
        } else if (recommendations.length > 0) {
            playRecommendation(0);
        }
    } else {
        if (recommendations.length > 0) {
            playRecommendation(0);
        } else if (queueIndex < queue.length - 1) {
            playSong(queueIndex + 1);
        }
    }
}

async function fetchRecommendations(videoId) {
    if (!videoId) return;
    try {
        const resp = await fetch(`/api/recommendations?videoId=${encodeURIComponent(videoId)}&limit=25`);
        const data = await resp.json();
        recommendations = (data.tracks || [])
            .filter(t => t.id !== currentSong?.id)
            .filter(t => !playedRecently.has(t.id));
        if (upNextOpen) renderUpNext();
    } catch (err) {
        console.error("Recommendations failed:", err);
        recommendations = [];
    }
}

function renderUpNext() {
    const list = document.getElementById("upNextList");
    let html = '';

    if (userQueue.length > 0) {
        html += `<div class="up-next-divider">Next in Queue (${userQueue.length})</div>`;
        html += userQueue.map((s, i) => `
            <div class="song-row" onclick="playSongDirect(userQueue[${i}])">
                <img src="${s.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                <div class="info">
                    <div class="title">${esc(s.title)}${s.isExplicit ? '<span class="explicit-badge">E</span>' : ''}</div>
                    <div class="subtitle">${esc(s.artist)}${s.album ? ' &middot; ' + esc(s.album) : ''}</div>
                </div>
                <div class="duration">${s.duration || ''}</div>
                <button class="song-remove-btn" onclick="event.stopPropagation(); removeFromQueue(${i})" title="Remove">&#10005;</button>
            </div>
        `).join("");
    }

    if (queueSource === 'album') {
        const remaining = queue.slice(queueIndex + 1);
        if (remaining.length) {
            html += remaining.map((s, i) => `
                <div class="song-row" onclick="playSong(${queueIndex + 1 + i})">
                    <img src="${s.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                    <div class="info">
                        <div class="title">${esc(s.title)}${s.isExplicit ? '<span class="explicit-badge">E</span>' : ''}</div>
                        <div class="subtitle">${esc(s.artist)}${s.album ? ' &middot; ' + esc(s.album) : ''}</div>
                    </div>
                    <div class="duration">${s.duration || ''}</div>
                </div>
            `).join("");
        }
        if (recommendations.length) {
            html += `<div class="up-next-divider">Recommended</div>`;
            html += recommendations.map((s, i) => `
                <div class="song-row" onclick="playRecommendation(${i})">
                    <img src="${s.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                    <div class="info">
                        <div class="title">${esc(s.title)}${s.isExplicit ? '<span class="explicit-badge">E</span>' : ''}</div>
                        <div class="subtitle">${esc(s.artist)}${s.album ? ' &middot; ' + esc(s.album) : ''}</div>
                    </div>
                    <div class="duration">${s.duration || ''}</div>
                    ${kebabBtn(s)}
                </div>
            `).join("");
        }
    } else {
        if (recommendations.length) {
            html += recommendations.map((s, i) => `
                <div class="song-row" onclick="playRecommendation(${i})">
                    <img src="${s.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                    <div class="info">
                        <div class="title">${esc(s.title)}${s.isExplicit ? '<span class="explicit-badge">E</span>' : ''}</div>
                        <div class="subtitle">${esc(s.artist)}${s.album ? ' &middot; ' + esc(s.album) : ''}</div>
                    </div>
                    <div class="duration">${s.duration || ''}</div>
                    ${kebabBtn(s)}
                </div>
            `).join("");
        }
    }

    if (!html) {
        html = `<div class="empty-state">No upcoming tracks</div>`;
    }

    list.innerHTML = html;
}

function playRecommendation(index) {
    if (index < 0 || index >= recommendations.length) return;
    if (currentSong && currentSong.id !== recommendations[index].id && !historyNavigating) {
        logPlayCompletion(currentSong, songCompleted, !songCompleted);
        pushToHistory(currentSong);
    }
    audioErrorRetried = false;
    const song = recommendations[index];
    const quality = document.getElementById("qualitySelect").value;
    const clean = document.getElementById("cleanToggle").checked;

    queue = recommendations;
    queueIndex = index;
    queueSource = 'other';
    currentSong = song;
    songCompleted = false;
    songStartTime = Date.now();
    playedRecently.add(song.id);
    if (playedRecently.size > 5) playedRecently.delete([...playedRecently][0]);

    document.getElementById("playerTitle").textContent = song.title;
    document.getElementById("playerArtist").textContent = song.artist || "Loading...";
    document.getElementById("playerThumb").src = song.thumbnail || '';
    document.getElementById("playerAlbumName").textContent = song.album || '';
    document.getElementById("playerAlbumName").style.pointerEvents = song.album_id ? "cursor" : "default";
    playerDiv.classList.remove("hidden");
    document.getElementById("playPauseBtn").classList.add("buffering");
    hideCleanNote();
    closeKebabMenu();

    audio.src = streamUrl(song, quality, clean);
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
    logPlay(song);
    updateLikeButton();
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
    const userDropdown = document.getElementById("userDropdown");
    const userMenu = document.querySelector(".user-menu");
    if (userDropdown && !userDropdown.classList.contains("hidden")) {
        if (!userDropdown.contains(e.target) && !userMenu.contains(e.target)) {
            userDropdown.classList.add("hidden");
        }
    }
    const songMenu = document.getElementById("songMenu");
    const songKebabBtn = document.querySelector(".song-kebab-btn:hover");
    if (songMenu && !songMenu.contains(e.target) && !e.target.closest(".song-kebab-btn")) {
        closeSongMenu();
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
let audioErrorRetried = false;

function audioDuration() {
    if (Number.isFinite(audio.duration) && audio.duration > 0) return audio.duration;
    if (audio.seekable && audio.seekable.length) return audio.seekable.end(audio.seekable.length - 1);
    if (currentSong && Number.isFinite(currentSong.duration_seconds) && currentSong.duration_seconds > 0) {
        return currentSong.duration_seconds;
    }
    return 0;
}

function playAudio(song) {
    audioErrorRetried = false;
}

let scrubbing = false;

function startScrub() {
    scrubbing = true;
}

function endScrub(el) {
    scrubbing = false;
    seekAudio(el.value);
}

function seekAudio(pct) {
    const duration = audioDuration();
    if (duration > 0) {
        audio.currentTime = (pct / 100) * duration;
    }
}

function skipForward() {
    const duration = audioDuration();
    if (duration > 0) {
        audio.currentTime = Math.min(audio.currentTime + 10, duration);
    }
}

function skipBackward() {
    audio.currentTime = Math.max(audio.currentTime - 10, 0);
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

/* === Navigation === */
function showHome() {
    mainContext = "home";
    const detailView = document.getElementById("mixDetailView");
    const homeContent = document.getElementById("homeContent");
    if (detailView && !detailView.classList.contains("hidden")) {
        detailView.classList.add("hidden");
        if (homeContent) homeContent.classList.remove("hidden");
    }
    document.getElementById("homeView").classList.remove("hidden");
    document.getElementById("searchView").classList.add("hidden");
    document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
    document.querySelector(".nav-btn:first-child").classList.add("active");
    loadHomeFeed();
}

function showSearch() {
    mainContext = "search";
    document.getElementById("homeView").classList.add("hidden");
    document.getElementById("searchView").classList.remove("hidden");
    document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
    document.querySelector(".nav-btn:nth-child(2)").classList.add("active");
}

/* === Home Feed === */
async function loadHomeFeed() {
    const container = document.getElementById("homeContent");
    container.innerHTML = `<div class="loading">Loading your personalized feed...</div>`;

    const greeting = document.getElementById("homeGreeting");
    const hour = new Date().getHours();
    const timeStr = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
    greeting.innerHTML = `<h2>${timeStr}${currentUser ? ", " + esc(currentUser.username) : ""}</h2>`;

    if (!authToken) {
        container.innerHTML = `
            <div class="home-section">
                <div class="home-section-header"><h3>Welcome to SampleAudio</h3></div>
                <div class="profile-empty">
                    <h3>Login to get started</h3>
                    <p>Sign in to see your Daily Mixes, Discovery recommendations, and personalized suggestions.</p>
                    <a href="/login.html" class="mix-play-btn" style="display:inline-block;text-decoration:none;position:static;opacity:1;transform:none">&#128269; Login</a>
                </div>
            </div>`;
        return;
    }

    try {
        container.innerHTML = await fetchHomeFeed();
    } catch (err) {
        container.innerHTML = `<div class="empty-state">Failed to load feed. Please try again.</div>`;
    }
}

async function fetchHomeFeed() {
    const [recent, dailyMixes, discovery, becauseLiked, albums, artists, charts, hotHits, genres] = await Promise.all([
        authFetch("/api/user/recently-played").then(r => r.ok ? r.json() : {tracks: []}),
        authFetch("/api/user/daily-mix").then(r => r.ok ? r.json() : {mixes: []}),
        authFetch("/api/user/mixes/discovery").then(r => r.ok ? r.json() : {mix: null}),
        authFetch("/api/user/mixes/because-you-liked").then(r => r.ok ? r.json() : {suggestions: []}),
        authFetch("/api/user/mixes/albums").then(r => r.ok ? r.json() : {albums: []}),
        authFetch("/api/user/mixes/new-artists").then(r => r.ok ? r.json() : {artists: []}),
        authFetch("/api/charts").then(r => r.ok ? r.json() : {charts: []}),
        authFetch("/api/hot-hits").then(r => r.ok ? r.json() : {hits: []}),
        authFetch("/api/user/mixes/genre-charts").then(r => r.ok ? r.json() : {genres: []}),
    ]);

    homeFeedData.recent = (recent.tracks || []).map(t => ({ ...t, id: t.id || t.video_id }));
    homeFeedData.mixes = dailyMixes.mixes || [];
    homeFeedData.discovery = discovery.mix || null;
    homeFeedData.because = becauseLiked.suggestions || [];
    homeFeedData.albums = albums.albums || [];
    homeFeedData.artists = artists.artists || [];
    homeFeedData.charts = charts.charts || [];
    homeFeedData.hotHits = hotHits.hits || [];
    homeFeedData.genres = genres.genres || [];
    homeFeedData.genrePersonalized = !!genres.personalized;
    homeFeedExpanded.clear();

    let html = "";

    if (homeFeedData.genres.length) {
        html += renderGenreSection(false);
    }

    if (homeFeedData.hotHits.length) {
        html += renderHotHitsSection(false);
    }

    if (homeFeedData.mixes.length) {
        html += renderDailyMixesSection(false);
    }

    if (homeFeedData.charts.length) {
        html += renderChartsSection(false);
    }

    if (homeFeedData.recent.length) {
        html += renderRecentlyPlayedSection(false);
    }

    if (homeFeedData.because.length) {
        html += renderBecauseYouLikedSection(false);
    }

    if (homeFeedData.albums.length) {
        html += renderAlbumSuggestionsSection(false);
    }

    if (homeFeedData.artists.length) {
        html += renderNewArtistsSection(false);
    }

    if (!html) {
        html = `<div class="profile-empty">
            <h3>Start Listening!</h3>
            <p>Play some songs to get personalized Daily Mixes, artist recommendations, and album suggestions.</p>
            <button class="mix-play-btn" style="position:static;opacity:1;transform:none" onclick="showSearch()">&#128269; Search Songs</button>
        </div>`;
    }

    return html;
}

let homeRefreshTimer = null;

function refreshHomeFeedQuiet() {
    if (homeRefreshTimer) return;
    homeRefreshTimer = setTimeout(async () => {
        homeRefreshTimer = null;
        const container = document.getElementById("homeContent");
        const homeView = document.getElementById("homeView");
        if (!container || !homeView || homeView.classList.contains("hidden")) return;
        try {
            container.innerHTML = await fetchHomeFeed();
        } catch (err) {
            // keep the existing feed on failure
        }
    }, 1500);
}

const BADGE_COLORS = ["#ffd700", "#00e5ff", "#ff4d6d", "#7cff6b", "#ffa726", "#c792ea", "#4dd0e1", "#ff8a80"];

function hiRes(url) {
    if (!url) return "";
    return url
        .replace(/=w\d+-h\d+/, "=w544-h544")
        .replace(/hqdefault\.jpg/, "maxresdefault.jpg")
        .replace(/mqdefault\.jpg/, "maxresdefault.jpg");
}

function numBadge(n, pos) {
    const c = BADGE_COLORS[(n - 1) % BADGE_COLORS.length];
    return `<span class="num-badge num-badge-${pos}" style="color:${c};border-color:${c}">#${n}</span>`;
}

function sectionHeader(title, subtitle, key, expanded) {
    const chev = key
        ? `<button class="section-chevron" onclick="toggleSection('${key}')" title="${expanded ? "Show Less" : "Show More"}">${expanded ? "&#10094;" : "&#10095;"}</button>`
        : "";
    return `<div class="home-section-header"><h3>${title}</h3>${subtitle ? `<span class="section-subtitle">${subtitle}</span>` : ""}${chev}</div>`;
}

function songRowHTML(s, action) {
    return `
        <div class="song-row" onclick="${action}">
            <img src="${s.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
            <div class="info">
                <div class="title">${esc(s.title || "Unknown")}</div>
                <div class="subtitle">${esc(s.artist || "")}${s.album ? ' &middot; ' + esc(s.album) : ''}</div>
            </div>
            <div class="duration">${s.duration || ''}</div>
            ${kebabBtn(s)}
        </div>`;
}

function toggleSection(key) {
    if (homeFeedExpanded.has(key)) homeFeedExpanded.delete(key);
    else homeFeedExpanded.add(key);
    const el = document.getElementById("sec_" + key);
    if (el) el.outerHTML = sectionHTML(key);
}

function sectionHTML(key) {
    const expanded = homeFeedExpanded.has(key);
    switch (key) {
        case "recent": return renderRecentlyPlayedSection(expanded);
        case "daily": return renderDailyMixesSection(expanded);
        case "genres": return renderGenreSection(expanded);
        case "hot_hits": return renderHotHitsSection(expanded);
        case "charts": return renderChartsSection(expanded);
        case "discovery": return renderDiscoveryMixSection(expanded);
        case "because": return renderBecauseYouLikedSection(expanded);
        case "albums": return renderAlbumSuggestionsSection(expanded);
        case "artists": return renderNewArtistsSection(expanded);
    }
    return "";
}

function renderRecentlyPlayedSection(expanded) {
    const tracks = homeFeedData.recent;
    if (!tracks.length) return "";
    const shown = expanded ? tracks : tracks.slice(0, 6);
    queue = tracks;
    queueSource = 'other';
    let html = `<div class="home-section" id="sec_recent">
        ${sectionHeader("&#128337; Recently Played", "Songs you have listened to", "recent", expanded)}
        <div class="suggestion-grid">`;
    shown.forEach((t, i) => {
        html += `
            <div class="suggestion-card" onclick="playSong(${i})">
                <img src="${t.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                <div class="card-title">${esc(t.title || "Unknown")}</div>
                <div class="card-subtitle">${esc(t.artist || "")}</div>
            </div>`;
    });
    html += `</div></div>`;
    return html;
}

function renderDailyMixesSection(expanded) {
    const mixes = homeFeedData.mixes;
    if (!mixes.length) return "";
    const discovery = (homeFeedData.discovery && homeFeedData.discovery.tracks && homeFeedData.discovery.tracks.length)
        ? homeFeedData.discovery : null;
    let html = `<div class="home-section" id="sec_daily">${sectionHeader("&#127925; Daily Mixes", "", "daily", expanded)}`;
    if (!expanded) {
        html += `<div class="mix-grid">`;
        if (discovery) {
            html += `
                <div class="mix-card" onclick="openMixDetail('discovery', 0)">
                    <img src="${mixThumb(discovery)}" alt="" loading="lazy" onerror="this.style.background='#333'">
                    <button class="mix-play-btn" onclick="event.stopPropagation(); playMix('discovery', 0)">&#9654;</button>
                    <div class="mix-title">${esc(discovery.name || "Discovery Mix")}</div>
                    <div class="mix-subtitle">${discovery.tracks.length} tracks</div>
                </div>`;
        }
        mixes.forEach((mix, i) => {
            const basedOn = (mix.based_on || []).join(", ");
            html += `
                <div class="mix-card" onclick="openMixDetail('daily', ${i})">
                    <img src="${mixThumb(mix)}" alt="" loading="lazy" onerror="this.style.background='#333'">
                    <button class="mix-play-btn" onclick="event.stopPropagation(); playMix('daily', ${i})">&#9654;</button>
                    <div class="mix-title">${esc(mix.name)}</div>
                    <div class="mix-subtitle">${esc(basedOn)}</div>
                </div>`;
        });
        html += `</div>`;
    } else {
        if (discovery) {
            html += `<div class="mix-track-section-title">${esc(discovery.name || "Discovery Mix")} &middot; ${discovery.tracks.length} tracks</div>`;
            html += (discovery.tracks || []).map((t, j) => songRowHTML(t, `playMixTrack('discovery', 0, ${j})`)).join("");
        }
        mixes.forEach((mix, i) => {
            const basedOn = (mix.based_on || []).join(", ");
            html += `<div class="mix-track-section-title">${esc(mix.name)}${basedOn ? ' &middot; ' + esc(basedOn) : ''}</div>`;
            html += (mix.tracks || []).map((t, j) => songRowHTML(t, `playMixTrack('daily', ${i}, ${j})`)).join("");
        });
    }
    return html + `</div>`;
}

function mixThumb(mix) {
    const t = (mix.tracks || []).find(x => x && x.thumbnail) || (mix.tracks || [])[0] || {};
    return hiRes(t.thumbnail || "");
}

function renderGenreSection(expanded) {
    const genres = homeFeedData.genres;
    if (!genres.length) return "";
    const title = homeFeedData.genrePersonalized
        ? "&#127760; Your Genres"
        : "&#127925; Moods & Genres";
    const subtitle = homeFeedData.genrePersonalized
        ? "Official charts for the genres you listen to"
        : "Official playlists by mood";
    let html = `<div class="home-section" id="sec_genres">${sectionHeader(title, subtitle, "genres", expanded)}`;
    if (!expanded) {
        html += `<div class="mix-grid">`;
        genres.forEach((g, i) => {
            html += `
                <div class="mix-card" onclick="openMixDetail('genres', ${i})">
                    <img src="${mixThumb(g)}" alt="" loading="lazy" onerror="this.style.background='#333'">
                    <button class="mix-play-btn" onclick="event.stopPropagation(); playMixTrack('genres', ${i}, 0)">&#9654;</button>
                    <div class="mix-title">${esc(g.name)}</div>
                    <div class="mix-subtitle">${g.tracks.length} tracks</div>
                </div>`;
        });
        html += `</div>`;
    } else {
        genres.forEach((g, i) => {
            html += `<div class="mix-track-section-title">${esc(g.name)} &middot; ${g.tracks.length} tracks</div>`;
            html += (g.tracks || []).map((t, j) => songRowHTML(t, `playMixTrack('genres', ${i}, ${j})`)).join("");
        });
    }
    return html + `</div>`;
}

function renderHotHitsSection(expanded) {
    const hits = homeFeedData.hotHits;
    if (!hits.length) return "";
    let html = `<div class="home-section" id="sec_hot_hits">${sectionHeader("&#128293; Hot Hits", "", "hot_hits", expanded)}`;
    if (!expanded) {
        html += `<div class="mix-grid">`;
        hits.forEach((c, i) => {
            html += `
                <div class="mix-card" onclick="openMixDetail('hot_hits', ${i})">
                    <img src="${mixThumb(c)}" alt="" loading="lazy" onerror="this.style.background='#333'">
                    <button class="mix-play-btn" onclick="event.stopPropagation(); playMixTrack('hot_hits', ${i}, 0)">&#9654;</button>
                    <div class="mix-title">${esc(c.name)}</div>
                    <div class="mix-subtitle">${c.tracks.length} tracks</div>
                </div>`;
        });
        html += `</div>`;
    } else {
        hits.forEach((c, i) => {
            html += `<div class="mix-track-section-title">${esc(c.name)} &middot; ${c.tracks.length} tracks</div>`;
            html += (c.tracks || []).map((t, j) => songRowHTML(t, `playMixTrack('hot_hits', ${i}, ${j})`)).join("");
        });
    }
    return html + `</div>`;
}

function renderChartsSection(expanded) {
    const charts = homeFeedData.charts;
    if (!charts.length) return "";
    let html = `<div class="home-section" id="sec_charts">${sectionHeader("&#127881; Charts", "", "charts", expanded)}`;    if (!expanded) {
        html += `<div class="mix-grid">`;
        charts.forEach((c, i) => {
            html += `
                <div class="mix-card" onclick="openMixDetail('charts', ${i})">
                    <img src="${mixThumb(c)}" alt="" loading="lazy" onerror="this.style.background='#333'">
                    <button class="mix-play-btn" onclick="event.stopPropagation(); playMixTrack('charts', ${i}, 0)">&#9654;</button>
                    <div class="mix-title">${esc(c.name)}</div>
                    <div class="mix-subtitle">${c.tracks.length} tracks</div>
                </div>`;
        });
        html += `</div>`;
    } else {
        charts.forEach((c, i) => {
            html += `<div class="mix-track-section-title">${esc(c.name)} &middot; ${c.tracks.length} tracks</div>`;
            html += (c.tracks || []).map((t, j) => songRowHTML(t, `playMixTrack('charts', ${i}, ${j})`)).join("");
        });
    }
    return html + `</div>`;
}

function renderDiscoveryMixSection(expanded) {
    const mix = homeFeedData.discovery;
    if (!mix || !mix.tracks || !mix.tracks.length) return "";
    const thumb = hiRes(mix.tracks[0].thumbnail || "");
    let html = `<div class="home-section" id="sec_discovery">
        ${sectionHeader("&#127758; Discovery Mix", "New music tailored for you", "discovery", expanded)}`;
    if (!expanded) {
        html += `<div class="mix-grid">
            <div class="mix-card" onclick="playMix('discovery', 0)">
                <img src="${thumb}" alt="" loading="lazy" onerror="this.style.background='#333'">
                <button class="mix-play-btn" onclick="event.stopPropagation(); playMix('discovery', 0)">&#9654;</button>
                <div class="mix-title">${esc(mix.name || "Discovery Mix")}</div>
                <div class="mix-subtitle">${mix.tracks.length} tracks</div>
            </div>
        </div>`;
    } else {
        html += (mix.tracks || []).map((t, j) => songRowHTML(t, `playMixTrack('discovery', 0, ${j})`)).join("");
    }
    return html + `</div>`;
}

function becauseTileHTML(t, cardIndex, trackIndex) {
    return `
        <div class="seed-tile" onclick="event.stopPropagation(); playMixTrack('because', ${cardIndex}, ${trackIndex})">
            <img src="${t.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
            ${numBadge(trackIndex + 1, "bl")}
        </div>`;
}

function renderBecauseYouLikedSection(expanded) {
    const suggestions = homeFeedData.because;
    if (!suggestions.length) return "";
    let html = `<div class="home-section" id="sec_because">${sectionHeader("&#10084;&#65039; Because You Liked", "", "because", expanded)}`;
    if (!expanded) {
        html += `<div class="mix-grid">`;
        suggestions.slice(0, 10).forEach((s, i) => {
            const first = (s.tracks || [])[0] || {};
            const cover = hiRes(first.thumbnail || "");
            html += `
                <div class="mix-card" onclick="openMixDetail('because', ${i})">
                    <div class="thumb-wrap">
                        <img src="${cover}" alt="" class="square" loading="lazy" onerror="this.style.background='#333'">
                        ${numBadge(1, "bl")}
                    </div>
                    <button class="mix-play-btn" onclick="event.stopPropagation(); playBecauseLiked(${i})">&#9654;</button>
                    <div class="mix-title">${esc(s.seed_title || "Because You Liked")}</div>
                    <div class="mix-subtitle">${(s.tracks || []).length} songs</div>
                </div>`;
        });
        html += `</div>`;
    } else {
        suggestions.forEach((s, i) => {
            html += `<div class="mix-track-section-title">${esc(s.seed_title)} &middot; ${(s.tracks || []).length} songs</div>`;
            html += `<div class="seed-thumbs">${(s.tracks || []).map((t, j) => becauseTileHTML(t, i, j)).join("")}</div>`;
        });
    }
    return html + `</div>`;
}

function renderAlbumSuggestionsSection(expanded) {
    const albums = homeFeedData.albums;
    if (!albums.length) return "";
    const shown = expanded ? albums : albums.slice(0, ALBUM_LIMIT);
    let html = `<div class="home-section" id="sec_albums">${sectionHeader("&#128193; Albums For You", "", "albums", expanded)}<div class="suggestion-grid">`;
    shown.forEach(a => {
        html += `
            <div class="suggestion-card" onclick="openAlbum('${a.album_id}')">
                <img src="${a.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                <div class="card-title">${esc(a.album)}</div>
                <div class="card-subtitle">${esc(a.artist)}</div>
            </div>`;
    });
    html += `</div></div>`;
    return html;
}

function renderNewArtistsSection(expanded) {
    const artists = homeFeedData.artists;
    if (!artists.length) return "";
    const shown = expanded ? artists : artists.slice(0, ARTIST_LIMIT);
    let html = `<div class="home-section" id="sec_artists">${sectionHeader("&#127908; New Artists", "", "artists", expanded)}<div class="suggestion-grid">`;
    shown.forEach((a, i) => {
        html += `
            <div class="suggestion-card" onclick="openArtist('${a.artist_id}')">
                <div class="thumb-wrap">
                    <img src="${a.thumbnail || ''}" alt="" class="square" loading="lazy" onerror="this.style.background='#333'">
                    ${numBadge(i + 1, "br")}
                </div>
                <div class="card-title">${esc(a.artist_name)}</div>
                <div class="card-subtitle">From ${esc(a.based_on)}</div>
            </div>`;
    });
    html += `</div></div>`;
    return html;
}

function playMixTrack(type, mixIndex, trackIndex) {
    let tracks = null;
    if (type === 'daily') {
        const mix = homeFeedData.mixes[mixIndex];
        if (mix) tracks = mix.tracks;
    } else if (type === 'discovery') {
        const mix = homeFeedData.discovery;
        if (mix) tracks = mix.tracks;
    } else if (type === 'because') {
        const s = homeFeedData.because[mixIndex];
        if (s) tracks = s.tracks;
    } else if (type === 'charts') {
        const c = homeFeedData.charts[mixIndex];
        if (c) tracks = c.tracks;
    } else if (type === 'hot_hits') {
        const c = homeFeedData.hotHits[mixIndex];
        if (c) tracks = c.tracks;
    } else if (type === 'genres') {
        const c = homeFeedData.genres[mixIndex];
        if (c) tracks = c.tracks;
    }
    if (!tracks || !tracks.length) return;
    queue = tracks;
    queueSource = (type === 'daily' ? 'daily-mix' : type === 'discovery' ? 'discovery' : type === 'charts' ? 'charts' : type === 'hot_hits' ? 'hot-hits' : type === 'genres' ? 'genres' : 'because-liked');
    enqueueMixTracks(queue.slice(1));
    playSong(trackIndex);
}

/* === Mix Detail Page === */
function openMixDetail(type, mixIndex) {
    let title = "", subtitle = "", tracks = null;
    if (type === 'daily') {
        const mix = homeFeedData.mixes[mixIndex];
        if (!mix) return;
        title = mix.name || "Daily Mix";
        subtitle = (mix.based_on || []).join(", ");
        tracks = mix.tracks || [];
    } else if (type === 'discovery') {
        const mix = homeFeedData.discovery;
        if (!mix) return;
        title = mix.name || "Discovery Mix";
        subtitle = "New music tailored for you";
        tracks = mix.tracks || [];
    } else if (type === 'because') {
        const s = homeFeedData.because[mixIndex];
        if (!s) return;
        title = s.seed_title || "Because You Liked";
        subtitle = "Suggested by your likes";
        tracks = s.tracks || [];
    } else if (type === 'charts') {
        const c = homeFeedData.charts[mixIndex];
        if (!c) return;
        title = c.name || "Charts";
        subtitle = "YouTube Music Charts";
        tracks = c.tracks || [];
    } else if (type === 'hot_hits') {
        const c = homeFeedData.hotHits[mixIndex];
        if (!c) return;
        title = c.name || "Hot Hits";
        subtitle = "Trending hits, updated regularly";
        tracks = c.tracks || [];
    } else if (type === 'genres') {
        const c = homeFeedData.genres[mixIndex];
        if (!c) return;
        title = c.name || "Genre";
        subtitle = homeFeedData.genrePersonalized ? "Matched to your taste" : "Official YouTube Music playlist";
        tracks = c.tracks || [];
    }
    if (!tracks.length) return;

    document.getElementById("homeContent").classList.add("hidden");
    const view = document.getElementById("mixDetailView");
    view.classList.remove("hidden");
    view.innerHTML = `
        <button class="back-btn" onclick="closeMixDetail()">&larr; Back</button>
        <div class="artist-header">
            <div>
                <h2>${esc(title)}</h2>
                <div style="color:#888;margin-top:4px">${esc(subtitle)} &middot; ${tracks.length} songs</div>
            </div>
            <button class="mix-play-btn" onclick="playMixTrack('${type}', ${mixIndex}, 0)" title="Play all">&#9654; Play</button>
        </div>
        <div class="section-title">Songs</div>
        ${tracks.map((t, i) => `
            <div class="song-row" onclick="playMixTrack('${type}', ${mixIndex}, ${i})">
                <img src="${t.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                <div class="info">
                    <div class="title">${esc(t.title || "Unknown")}</div>
                    <div class="subtitle">${esc(t.artist || "")}${t.album ? ' &middot; ' + esc(t.album) : ''}</div>
                </div>
                <div class="duration">${t.duration || ''}</div>
                ${kebabBtn(t)}
            </div>
        `).join("")}`;
}

function closeMixDetail() {
    document.getElementById("mixDetailView").classList.add("hidden");
    document.getElementById("homeContent").classList.remove("hidden");
}

/* === Play Mix from Home === */
function enqueueMixTracks(tracks) {
    userQueue.length = 0;
    for (const t of tracks) {
        if (userQueue.length >= 50) break;
        t._autoQueued = true;
        userQueue.push(t);
    }
    if (!upNextOpen) toggleUpNext();
    renderUpNext();
}

function clearStaleQueueItems() {
    if (!userQueue.some(s => s._autoQueued)) return;
    userQueue = userQueue.filter(s => !s._autoQueued);
    if (upNextOpen) renderUpNext();
}

async function playMix(type, index) {
    let data;
    if (type === "daily") {
        const resp = await authFetch("/api/user/daily-mix");
        data = await resp.json();
        if (data.mixes && data.mixes[index]) {
            queue = data.mixes[index].tracks;
            queueSource = 'daily-mix';
            if (queue.length > 0) {
                enqueueMixTracks(queue.slice(1));
                playSong(0);
            }
        }
    } else if (type === "discovery") {
        const resp = await authFetch("/api/user/mixes/discovery");
        data = await resp.json();
        if (data.mix && data.mix.tracks) {
            queue = data.mix.tracks;
            queueSource = 'discovery';
            if (queue.length > 0) {
                enqueueMixTracks(queue.slice(1));
                playSong(0);
            }
        }
    }
}

async function playBecauseLiked(index) {
    const resp = await authFetch("/api/user/mixes/because-you-liked");
    const data = await resp.json();
    if (data.suggestions && data.suggestions[index]) {
        queue = data.suggestions[index].tracks;
        queueSource = 'because-liked';
        if (queue.length > 0) {
            enqueueMixTracks(queue.slice(1));
            playSong(0);
        }
    }
}

/* === Initialize Auth on page load === */
let feedAutoRefreshTimer = null;

function startFeedAutoRefresh() {
    if (feedAutoRefreshTimer) return;
    feedAutoRefreshTimer = setInterval(() => {
        if (mainContext !== "home") return;
        const recentEl = document.getElementById("sec_recent");
        const artistsEl = document.getElementById("sec_artists");
        if (!recentEl && !artistsEl) return;
        Promise.all([
            authFetch("/api/user/recently-played").then(r => r.ok ? r.json() : {tracks: []}),
            authFetch("/api/user/mixes/new-artists").then(r => r.ok ? r.json() : {artists: []}),
        ]).then(([recent, artists]) => {
            homeFeedData.recent = (recent.tracks || []).map(t => ({ ...t, id: t.id || t.video_id }));
            homeFeedData.artists = artists.artists || [];
            if (recentEl && homeFeedData.recent.length) {
                recentEl.outerHTML = renderRecentSectionInline();
            } else if (recentEl) {
                recentEl.remove();
            }
            if (artistsEl && homeFeedData.artists.length) {
                artistsEl.outerHTML = renderArtistsSectionInline();
            } else if (artistsEl) {
                artistsEl.remove();
            }
        }).catch(() => {});
    }, 30000);
}

function renderRecentSectionInline() {
    const tracks = homeFeedData.recent;
    const shown = tracks.slice(0, 6);
    let html = `<div class="home-section" id="sec_recent">
        ${sectionHeader("&#128337; Recently Played", "Songs you have listened to", "recent", false)}
        <div class="suggestion-grid">`;
    shown.forEach((t, i) => {
        html += `
            <div class="suggestion-card" onclick="playSong(${i})">
                <img src="${t.thumbnail || ''}" alt="" loading="lazy" onerror="this.style.background='#333'">
                <div class="card-title">${esc(t.title || "Unknown")}</div>
                <div class="card-subtitle">${esc(t.artist || "")}</div>
            </div>`;
    });
    html += `</div></div>`;
    return html;
}

function renderArtistsSectionInline() {
    const artists = homeFeedData.artists;
    const shown = artists.slice(0, ARTIST_LIMIT);
    let html = `<div class="home-section" id="sec_artists">${sectionHeader("&#127908; New Artists", "", "artists", false)}<div class="suggestion-grid">`;
    shown.forEach((a, i) => {
        html += `
            <div class="suggestion-card" onclick="openArtist('${a.artist_id}')">
                <div class="thumb-wrap">
                    <img src="${a.thumbnail || ''}" alt="" class="square" loading="lazy" onerror="this.style.background='#333'">
                    ${numBadge(i + 1, "br")}
                </div>
                <div class="card-title">${esc(a.artist_name)}</div>
                <div class="card-subtitle">From ${esc(a.based_on)}</div>
            </div>`;
    });
    html += `</div></div>`;
    return html;
}

function safeInitAuth() {
    try {
        cacheDomElements();
        attachEventListeners();
        initAuth();
        if (authToken) {
            loadHomeFeed();
        }
    } catch (err) {
        console.error('Auth initialization failed:', err);
        // Fallback: retry after a short delay
        setTimeout(() => {
            try {
                cacheDomElements();
                attachEventListeners();
                initAuth();
                if (authToken) {
                    loadHomeFeed();
                }
            } catch (e) {
                console.error('Auth retry failed:', e);
            }
        }, 100);
    }
}

// Run immediately (DOM should be ready since script is at end of body)
safeInitAuth();

// Also run on DOMContentLoaded as fallback
document.addEventListener('DOMContentLoaded', safeInitAuth);
