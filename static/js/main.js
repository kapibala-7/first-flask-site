/* 《答案之书》交互、开场与彩蛋粒子，以及 Web Audio 音乐和提示音。 */
"use strict";

const questionInput = document.getElementById("questionInput");
const charCount = document.getElementById("charCount");
const askButton = document.getElementById("askButton");
const buttonText = document.getElementById("buttonText");
const errorMessage = document.getElementById("errorMessage");
const answerPanel = document.getElementById("answerPanel");
const eggParticleCanvas = document.getElementById("eggParticles");
const fateGateReveal = document.getElementById("fateGateReveal");
const eggRevealTitle = document.getElementById("eggRevealTitle");
const answerText = document.getElementById("answerText");
const answerCategory = document.getElementById("answerCategory");
const answerNote = document.getElementById("answerNote");
const reviewQuestionButton = document.getElementById("reviewQuestionButton");
const reviewStatus = document.getElementById("reviewStatus");
const askAgainButton = document.getElementById("askAgainButton");
const soundButton = document.getElementById("soundButton");
const soundIcon = document.getElementById("soundIcon");
const soundLabel = document.getElementById("soundLabel");
const bookCover = document.getElementById("bookCover");
const bookObject = document.getElementById("bookObject");
const bookStage = document.querySelector(".book-stage");
const pageWaiting = document.getElementById("pageWaiting");
const opening = document.getElementById("opening");
const skipOpeningButton = document.getElementById("skipOpening");
const openingStars = document.getElementById("openingStars");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const onboarding = document.getElementById("onboarding");
const mainContent = document.getElementById("mainContent");
const registerTab = document.getElementById("registerTab");
const returnTab = document.getElementById("returnTab");
const registerForm = document.getElementById("registerForm");
const returnForm = document.getElementById("returnForm");
const profileForms = document.getElementById("profileForms");
const profileError = document.getElementById("profileError");
const recoveryLabel = document.getElementById("recoveryLabel");
const recoveryCode = document.getElementById("recoveryCode");
const recoveryStage = document.getElementById("recoveryStage");
const recoveryDisplay = document.getElementById("recoveryDisplay");
const recoveryContinue = document.getElementById("recoveryContinue");
const birthdayGate = document.getElementById("birthdayGate");
const birthdayName = document.getElementById("birthdayName");
const birthdayMessage = document.getElementById("birthdayMessage");
const birthdayContinue = document.getElementById("birthdayContinue");
const userName = document.getElementById("userName");
const memorySummary = document.getElementById("memorySummary");
const switchUserButton = document.getElementById("switchUserButton");

let audioContext = null;
let soundEnabled = readSetting("answerBookSound") !== "off";
let requestInProgress = false;
let latestQuestion = "";
let userToken = readSetting("answerBookUserToken");
let nextDestination = "onboarding";
let pendingRegistrationToken = null;
let openingTimer = null;
let animationFrame = null;
let starParticles = [];
let eggParticleFrame = null;
let eggParticles = [];
const activeOscillators = new Set();
const ambientOscillators = new Set();
const ambientNodes = new Set();
let ambientMaster = null;
let ambientDelay = null;
let ambientStopTimer = null;
let ambientPhraseTimer = null;
let ambientBeatTimer = null;
const ambientNoteTimers = new Set();
let ambientMelodyIndex = 0;
let audioUnlocked = false;
let openingSoundPlayed = false;

function readSetting(key) {
    try {
        return localStorage.getItem(key);
    } catch (error) {
        return null;
    }
}

function saveSetting(key, value) {
    try {
        localStorage.setItem(key, value);
    } catch (error) {
        // 存储不可用时仅不记住偏好，不影响本次交互。
    }
}

function updateCharCount() {
    charCount.textContent = `${questionInput.value.length} / 500`;
}
questionInput.addEventListener("input", updateCharCount);

function updateSoundButton() {
    soundButton.setAttribute("aria-pressed", String(soundEnabled));
    soundButton.setAttribute(
        "aria-label",
        soundEnabled ? "背景音乐与音效已开启" : "背景音乐与音效已关闭"
    );
    soundIcon.textContent = soundEnabled ? "♫" : "♪";
    soundLabel.textContent = soundEnabled ? "音乐与音效已开启" : "音乐与音效已关闭";
}
updateSoundButton();

function getAudioContext() {
    if (!soundEnabled) return null;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return null;
    if (!audioContext) audioContext = new AudioContextClass();
    if (audioContext.state === "suspended") {
        audioContext.resume().catch(() => {});
    }
    return audioContext;
}

function stopScheduledSound() {
    activeOscillators.forEach((oscillator) => {
        try {
            oscillator.stop();
        } catch (error) {
            if (error.name !== "InvalidStateError") throw error;
        }
    });
    activeOscillators.clear();
}

function playSceneSound(scene = "answer") {
    const ctx = getAudioContext();
    if (!ctx) return;
    const tones = {
        opening: [261.63, 392, 587.33],
        open: [392, 587.33],
        flip: [392, 523.25],
        click: [659.25],
        answer: [523.25, 659.25],
        rare: [523.25, 659.25, 783.99, 1046.5],
        birthday: [523.25, 659.25, 783.99, 1046.5],
        gate: [392, 523.25, 659.25],
        moon: [392, 587.33, 880, 1174.66],
        starlight: [783.99, 1046.5],
        magic: [659.25, 523.25, 783.99, 1046.5],
        whisper: [392, 440, 523.25],
        constellation: [523.25, 659.25, 783.99],
        visit: [523.25, 783.99, 1046.5, 783.99],
        comet: [1046.5, 783.99, 523.25]
    };
    const frequencies = tones[scene] || tones.answer;
    const now = ctx.currentTime;
    const duration = scene === "birthday" || scene === "moon" ? .62 : .42;
    frequencies.forEach((frequency, index) => {
        const oscillator = ctx.createOscillator();
        const gain = ctx.createGain();
        const startAt = now + index * (duration > .42 ? .12 : .08);
        const triangleScenes = [
            "birthday", "gate", "magic", "constellation", "visit"
        ];
        oscillator.type = triangleScenes.includes(scene) ? "triangle" : "sine";
        oscillator.frequency.setValueAtTime(frequency, startAt);
        gain.gain.setValueAtTime(.0001, startAt);
        gain.gain.exponentialRampToValueAtTime(scene === "birthday" ? .032 : .045, startAt + .035);
        gain.gain.exponentialRampToValueAtTime(.0001, startAt + duration);
        oscillator.connect(gain);
        gain.connect(ctx.destination);
        oscillator.addEventListener("ended", () => activeOscillators.delete(oscillator), { once: true });
        activeOscillators.add(oscillator);
        oscillator.start(startAt);
        oscillator.stop(startAt + duration + .01);
    });
}

function stopEggParticles() {
    if (eggParticleFrame !== null) {
        window.cancelAnimationFrame(eggParticleFrame);
        eggParticleFrame = null;
    }
    eggParticles = [];
    const context = eggParticleCanvas.getContext("2d");
    if (context) {
        context.setTransform(1, 0, 0, 1, 0, 0);
        context.clearRect(0, 0, eggParticleCanvas.width, eggParticleCanvas.height);
    }
}

function launchEggParticles(eggId) {
    stopEggParticles();
    if (reducedMotion.matches || document.hidden) return;

    const bounds = eggParticleCanvas.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
    eggParticleCanvas.width = Math.round(bounds.width * ratio);
    eggParticleCanvas.height = Math.round(bounds.height * ratio);
    const context = eggParticleCanvas.getContext("2d");
    if (!context) return;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);

    const palettes = {
        "fate-gate": ["#fff1ad", "#ffc857", "#fffdf1"],
        "moonlit-key": ["#e5c8ff", "#a77cff", "#fffaff"],
        "star-letter": ["#d5edff", "#fff2ba", "#ffffff"],
        "small-magic": ["#f4d1ff", "#b58aff", "#fff0be"],
        "book-whisper": ["#fff4d5", "#d9c8ff", "#ffffff"],
        "constellation-choice": ["#fff2bd", "#c9b5ff", "#d9f1ff"],
        "third-visit": ["#f5d5ff", "#bd8aff", "#fff8e5"],
        "rare-comet": ["#ffffff", "#d4c0ff", "#a9dcff"]
    };
    const palette = palettes[eggId] || palettes["star-letter"];
    const count = Math.min(96, Math.max(44, Math.round(bounds.width / 4)));
    const centerX = bounds.width / 2;
    const centerY = bounds.height / 2;

    eggParticles = Array.from({ length: count }, () => {
        let angle = Math.random() * Math.PI * 2;
        let speed = Math.random() * 2.8 + 1;
        let x = centerX;
        let y = centerY;
        if (eggId === "rare-comet") {
            angle = -Math.PI / 4 + (Math.random() - .5) * .35;
            speed = Math.random() * 4 + 3;
            x = bounds.width * (Math.random() * .25);
            y = bounds.height * (.72 + Math.random() * .28);
        } else if (eggId === "star-letter") {
            x = Math.random() * bounds.width;
            y = -Math.random() * bounds.height * .3;
            angle = Math.PI / 2 + (Math.random() - .5) * .45;
            speed = Math.random() * 2 + 1;
        } else if (eggId === "book-whisper") {
            x = Math.random() * bounds.width;
            y = centerY + (Math.random() - .5) * 24;
            angle = (Math.random() - .5) * .3;
            speed = Math.random() * 2.2 + 1.3;
        } else if (eggId === "moonlit-key" || eggId === "small-magic") {
            const orbitAngle = Math.random() * Math.PI * 2;
            const orbitRadius = Math.random() * Math.min(bounds.width, bounds.height) * .34;
            x = centerX + Math.cos(orbitAngle) * orbitRadius;
            y = centerY + Math.sin(orbitAngle) * orbitRadius;
            angle = orbitAngle + (Math.random() < .5 ? Math.PI / 2 : -Math.PI / 2);
            speed = Math.random() * 2.4 + 1.3;
        } else if (eggId === "constellation-choice") {
            x = bounds.width * (.2 + Math.random() * .6);
            y = bounds.height * (.2 + Math.random() * .6);
            angle = Math.random() * Math.PI * 2;
            speed = Math.random() * 1.8 + .7;
        } else if (eggId === "third-visit") {
            const burstAngle = Math.random() * Math.PI * 2;
            x = centerX + Math.cos(burstAngle) * 8;
            y = centerY + Math.sin(burstAngle) * 8;
            angle = burstAngle;
            speed = Math.random() * 3.5 + 2;
        } else if (eggId === "fate-gate") {
            x += (Math.random() - .5) * 38;
            y = bounds.height * (.65 + Math.random() * .25);
            angle = -Math.PI / 2 + (Math.random() - .5) * 1.3;
            speed = Math.random() * 4 + 2.2;
        }
        return {
            x,
            y,
            vx: Math.cos(angle) * speed,
            vy: Math.sin(angle) * speed,
            size: Math.random() * 4.2 + 2.2,
            color: palette[Math.floor(Math.random() * palette.length)],
            rotation: Math.random() * Math.PI,
            spin: (Math.random() - .5) * .12,
            alpha: Math.random() * .45 + .55
        };
    });

    const startedAt = performance.now();
    let previousFrame = startedAt;
    function drawFrame(now) {
        if (document.hidden || reducedMotion.matches) {
            stopEggParticles();
            return;
        }
        const elapsed = now - startedAt;
        const step = Math.min((now - previousFrame) / 16.67, 2);
        previousFrame = now;
        const fade = Math.max(0, 1 - elapsed / 2200);
        context.clearRect(0, 0, bounds.width, bounds.height);
        context.globalCompositeOperation = "lighter";

        eggParticles.forEach((particle) => {
            particle.x += particle.vx * step;
            particle.y += particle.vy * step;
            particle.vy += .018 * step;
            particle.vx *= .992;
            particle.rotation += particle.spin * step;
            context.save();
            context.translate(particle.x, particle.y);
            context.rotate(particle.rotation);
            context.globalAlpha = fade * particle.alpha;
            context.fillStyle = particle.color;
            context.shadowColor = particle.color;
            context.shadowBlur = 10;
            context.beginPath();
            context.moveTo(0, -particle.size);
            context.lineTo(particle.size * .3, -particle.size * .3);
            context.lineTo(particle.size, 0);
            context.lineTo(particle.size * .3, particle.size * .3);
            context.lineTo(0, particle.size);
            context.lineTo(-particle.size * .3, particle.size * .3);
            context.lineTo(-particle.size, 0);
            context.lineTo(-particle.size * .3, -particle.size * .3);
            context.closePath();
            context.fill();
            context.restore();
        });

        if (elapsed < 2200) {
            eggParticleFrame = window.requestAnimationFrame(drawFrame);
        } else {
            context.globalCompositeOperation = "source-over";
            stopEggParticles();
        }
    }
    eggParticleFrame = window.requestAnimationFrame(drawFrame);
}

function startAmbient() {
    const ctx = getAudioContext();
    if (!ctx || ambientPhraseTimer !== null) return;
    if (ambientStopTimer !== null) {
        window.clearTimeout(ambientStopTimer);
        ambientStopTimer = null;
    }

    if (!ambientMaster) {
        ambientMaster = ctx.createGain();
        ambientMaster.gain.setValueAtTime(.0001, ctx.currentTime);
        ambientMaster.connect(ctx.destination);
        ambientDelay = ctx.createDelay(6);
        const delayFeedback = ctx.createGain();
        const delayWet = ctx.createGain();
        ambientDelay.delayTime.setValueAtTime(.48, ctx.currentTime);
        delayFeedback.gain.setValueAtTime(.24, ctx.currentTime);
        delayWet.gain.setValueAtTime(.2, ctx.currentTime);
        ambientMaster.connect(ambientDelay);
        ambientDelay.connect(delayWet);
        delayWet.connect(ctx.destination);
        ambientDelay.connect(delayFeedback);
        delayFeedback.connect(ambientDelay);
        ambientNodes.add(ambientMaster, ambientDelay, delayFeedback, delayWet);

        [130.81, 196, 261.63].forEach((frequency, index) => {
            const oscillator = ctx.createOscillator();
            const voice = ctx.createGain();
            oscillator.type = "sine";
            oscillator.frequency.setValueAtTime(frequency, ctx.currentTime);
            oscillator.detune.setValueAtTime(index === 2 ? -4 : 0, ctx.currentTime);
            voice.gain.setValueAtTime([.035, .018, .009][index], ctx.currentTime);
            oscillator.connect(voice);
            voice.connect(ambientMaster);
            oscillator.start();
            ambientOscillators.add(oscillator);
            ambientNodes.add(oscillator, voice);
        });

        const noiseBuffer = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
        const noiseData = noiseBuffer.getChannelData(0);
        for (let index = 0; index < noiseData.length; index += 1) {
            noiseData[index] = (Math.random() * 2 - 1) * .35;
        }
        const atmosphere = ctx.createBufferSource();
        const atmosphereFilter = ctx.createBiquadFilter();
        const atmosphereGain = ctx.createGain();
        atmosphere.buffer = noiseBuffer;
        atmosphere.loop = true;
        atmosphereFilter.type = "lowpass";
        atmosphereFilter.frequency.setValueAtTime(420, ctx.currentTime);
        atmosphereGain.gain.setValueAtTime(.012, ctx.currentTime);
        atmosphere.connect(atmosphereFilter);
        atmosphereFilter.connect(atmosphereGain);
        atmosphereGain.connect(ambientMaster);
        atmosphere.start();
        atmosphere.addEventListener("ended", () => ambientNodes.delete(atmosphere), { once: true });
        ambientNodes.add(atmosphere, atmosphereFilter, atmosphereGain);
    }
    ambientMaster.gain.cancelScheduledValues(ctx.currentTime);
    ambientMaster.gain.setValueAtTime(Math.max(ambientMaster.gain.value, .0001), ctx.currentTime);
    ambientMaster.gain.exponentialRampToValueAtTime(.4, ctx.currentTime + 1.4);

    const phrases = [
        [{ note: 392, at: 0 }, { note: 493.88, at: .42 }, { note: 587.33, at: .9 }],
        [{ note: 659.25, at: 0 }, { note: 587.33, at: .4 }, { note: 493.88, at: .86 }],
        [{ note: 440, at: 0 }, { note: 523.25, at: .48 }, { note: 493.88, at: .92 }, { note: 392, at: 1.35 }],
        [{ note: 783.99, at: 0 }, { note: 587.33, at: .58 }]
    ];

    const playPianoNote = (frequency) => {
        if (!ambientMaster || document.hidden || !soundEnabled) return;
        const startAt = ctx.currentTime;
        [1, 2, 3].forEach((partial, index) => {
            const oscillator = ctx.createOscillator();
            const voice = ctx.createGain();
            const warmth = ctx.createBiquadFilter();
            oscillator.type = "sine";
            oscillator.frequency.setValueAtTime(frequency * partial, startAt);
            warmth.type = "lowpass";
            warmth.frequency.setValueAtTime(1450, startAt);
            warmth.Q.setValueAtTime(.55, startAt);
            voice.gain.setValueAtTime(.0001, startAt);
            voice.gain.exponentialRampToValueAtTime([.082, .012, .0018][index], startAt + .035);
            voice.gain.exponentialRampToValueAtTime(.0001, startAt + [.62, .34, .2][index]);
            oscillator.connect(voice);
            voice.connect(warmth);
            warmth.connect(ambientMaster);
            oscillator.addEventListener("ended", () => {
                ambientOscillators.delete(oscillator);
                ambientNodes.delete(oscillator);
                ambientNodes.delete(voice);
                ambientNodes.delete(warmth);
            }, { once: true });
            oscillator.start(startAt);
            oscillator.stop(startAt + .52);
            ambientOscillators.add(oscillator);
            ambientNodes.add(oscillator, voice, warmth);
        });
    };

    const schedulePhrase = () => {
        if (!ambientMaster || document.hidden || !soundEnabled) return;
        const phrase = phrases[ambientMelodyIndex % phrases.length];
        const startDelay = ambientMelodyIndex === 0 ? 0 : 1800 + Math.random() * 1800;
        phrase.forEach(({ note, at }) => {
            const timer = window.setTimeout(() => {
                ambientNoteTimers.delete(timer);
                playPianoNote(note);
            }, startDelay + at * 1000);
            ambientNoteTimers.add(timer);
        });
        ambientMelodyIndex += 1;
        const phraseLength = phrase[phrase.length - 1].at * 1000;
        ambientPhraseTimer = window.setTimeout(schedulePhrase, startDelay + phraseLength + 2600 + Math.random() * 2600);
    };

    const playSoftBeat = () => {
        if (!ambientMaster || document.hidden || !soundEnabled) return;
        const startAt = ctx.currentTime;
        const drum = ctx.createOscillator();
        const drumGain = ctx.createGain();
        drum.type = "sine";
        drum.frequency.setValueAtTime(92, startAt);
        drum.frequency.exponentialRampToValueAtTime(48, startAt + .18);
        drumGain.gain.setValueAtTime(.0001, startAt);
        drumGain.gain.exponentialRampToValueAtTime(.045, startAt + .012);
        drumGain.gain.exponentialRampToValueAtTime(.0001, startAt + .24);
        drum.connect(drumGain);
        drumGain.connect(ambientMaster);
        drum.addEventListener("ended", () => {
            ambientOscillators.delete(drum);
            ambientNodes.delete(drum);
            ambientNodes.delete(drumGain);
        }, { once: true });
        drum.start(startAt);
        drum.stop(startAt + .25);
        ambientOscillators.add(drum);
        ambientNodes.add(drum, drumGain);
    };

    const scheduleBeat = () => {
        if (!ambientMaster || document.hidden || !soundEnabled) return;
        playSoftBeat();
        if (Math.random() < .24) {
            const doubleBeat = window.setTimeout(() => {
                ambientNoteTimers.delete(doubleBeat);
                playSoftBeat();
            }, 190 + Math.random() * 110);
            ambientNoteTimers.add(doubleBeat);
        }
        ambientBeatTimer = window.setTimeout(scheduleBeat, 2400 + Math.random() * 3000);
    };

    schedulePhrase();
    ambientBeatTimer = window.setTimeout(scheduleBeat, 1400 + Math.random() * 1200);
}

function stopAmbient(immediate = false) {
    if (!audioContext) return;
    if (ambientPhraseTimer !== null) {
        window.clearTimeout(ambientPhraseTimer);
        ambientPhraseTimer = null;
    }
    if (ambientBeatTimer !== null) {
        window.clearTimeout(ambientBeatTimer);
        ambientBeatTimer = null;
    }
    ambientNoteTimers.forEach((timer) => window.clearTimeout(timer));
    ambientNoteTimers.clear();
    if (ambientStopTimer !== null) {
        window.clearTimeout(ambientStopTimer);
        ambientStopTimer = null;
    }
    if (!ambientOscillators.size && !ambientMaster) return;
    const master = ambientMaster;
    if (master) {
        master.gain.cancelScheduledValues(audioContext.currentTime);
        master.gain.setValueAtTime(Math.max(master.gain.value, .0001), audioContext.currentTime);
        if (!immediate && audioContext.state === "running") {
            master.gain.exponentialRampToValueAtTime(.0001, audioContext.currentTime + .75);
        } else {
            master.gain.setValueAtTime(.0001, audioContext.currentTime);
        }
    }

    const stopVoices = () => {
        ambientOscillators.forEach((oscillator) => {
            try {
                oscillator.stop();
            } catch (error) {
                if (error.name !== "InvalidStateError") throw error;
            }
        });
        ambientOscillators.clear();
        ambientNodes.forEach((node) => {
            if (node instanceof AudioBufferSourceNode) {
                try {
                    node.stop();
                } catch (error) {
                    if (error.name !== "InvalidStateError") throw error;
                }
            }
            node.disconnect();
        });
        ambientNodes.clear();
        ambientDelay = null;
        if (ambientMaster === master) ambientMaster = null;
        ambientStopTimer = null;
    };
    if (immediate || audioContext.state !== "running") {
        stopVoices();
    } else {
        ambientStopTimer = window.setTimeout(stopVoices, 850);
    }
}

async function requestJson(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (options.authToken) headers.Authorization = `Bearer ${options.authToken}`;
    const response = await fetch(path, { ...options, headers });
    let data;
    try {
        data = await response.json();
    } catch (error) {
        throw new Error("服务器暂时无法读取请求，请稍后重试。");
    }
    return { response, data };
}

function revealDestination() {
    if (document.body.classList.contains("opening-active")) return;
    onboarding.hidden = nextDestination !== "onboarding";
    birthdayGate.hidden = nextDestination !== "birthday";
    mainContent.hidden = nextDestination !== "main";
    if (nextDestination === "birthday") playSceneSound("birthday");
}

function showProfileError(message) {
    profileError.textContent = message;
    profileError.hidden = false;
}

function clearProfileError() {
    profileError.hidden = true;
    profileError.textContent = "";
}

function setProfileForm(mode) {
    const isRegister = mode === "register";
    registerForm.hidden = !isRegister;
    returnForm.hidden = isRegister;
    registerTab.classList.toggle("is-active", isRegister);
    returnTab.classList.toggle("is-active", !isRegister);
    registerTab.setAttribute("aria-pressed", String(isRegister));
    returnTab.setAttribute("aria-pressed", String(!isRegister));
    recoveryLabel.hidden = true;
    recoveryCode.hidden = true;
    recoveryCode.required = false;
    recoveryCode.value = "";
    clearProfileError();
}

function saveUserToken(token) {
    userToken = token;
    saveSetting("answerBookUserToken", token);
}

function selectUserDestination(data) {
    userName.textContent = data.user.name;
    const discoveredCount = (data.discovered_eggs || []).length;
    memorySummary.textContent = `${discoveredCount} 条星海秘语 · 第 ${data.user.visit_count} 次来访`;
    birthdayName.textContent = data.user.name;
    birthdayMessage.textContent = data.birthday_message || "";
    nextDestination = data.birthday_pending ? "birthday" : "main";
    revealDestination();
}

async function loadCurrentUser(token) {
    const { response, data } = await requestJson("/api/users/me", {
        method: "GET",
        authToken: token
    });
    if (!response.ok || !data.ok) {
        throw new Error(data.message || "无法载入访客资料。");
    }
    return data;
}

async function initializeProfile() {
    if (!userToken) {
        nextDestination = "onboarding";
        revealDestination();
        return;
    }
    try {
        const data = await loadCurrentUser(userToken);
        selectUserDestination(data);
    } catch (error) {
        saveUserToken("");
        nextDestination = "onboarding";
        revealDestination();
    }
}

registerTab.addEventListener("click", () => setProfileForm("register"));
returnTab.addEventListener("click", () => setProfileForm("return"));

registerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearProfileError();
    const formData = new FormData(registerForm);
    const submitButton = registerForm.querySelector("button[type=submit]");
    submitButton.disabled = true;
    try {
        const { response, data } = await requestJson("/api/users/register", {
            method: "POST",
            body: JSON.stringify({
                name: formData.get("name"),
                birth_date: formData.get("birth_date")
            })
        });
        if (!response.ok || !data.ok) throw new Error(data.message || "登记失败，请重试。");
        pendingRegistrationToken = data.token;
        recoveryDisplay.textContent = data.recovery_code;
        profileForms.hidden = true;
        recoveryStage.hidden = false;
    } catch (error) {
        showProfileError(error.message || "登记暂时失败，请稍后重试。");
    } finally {
        submitButton.disabled = false;
    }
});

returnForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearProfileError();
    const formData = new FormData(returnForm);
    const submitButton = returnForm.querySelector("button[type=submit]");
    submitButton.disabled = true;
    try {
        const { response, data } = await requestJson("/api/users/identify", {
            method: "POST",
            body: JSON.stringify({
                name: formData.get("name"),
                birth_date: formData.get("birth_date"),
                recovery_code: formData.get("recovery_code")
            })
        });
        if (response.status === 409 && data.needs_recovery_code) {
            recoveryLabel.hidden = false;
            recoveryCode.hidden = false;
            recoveryCode.required = true;
            recoveryCode.focus();
            showProfileError(data.message);
            return;
        }
        if (!response.ok || !data.ok) throw new Error(data.message || "识别失败，请检查资料。");
        saveUserToken(data.token);
        selectUserDestination(await loadCurrentUser(data.token));
    } catch (error) {
        showProfileError(error.message || "无法连接服务，请稍后重试。");
    } finally {
        submitButton.disabled = false;
    }
});

recoveryContinue.addEventListener("click", async () => {
    if (!pendingRegistrationToken) return;
    saveUserToken(pendingRegistrationToken);
    pendingRegistrationToken = null;
    recoveryStage.hidden = true;
    profileForms.hidden = false;
    try {
        selectUserDestination(await loadCurrentUser(userToken));
    } catch (error) {
        saveUserToken("");
        nextDestination = "onboarding";
        showProfileError(error.message || "资料载入失败，请重新识别。");
        revealDestination();
    }
});

birthdayContinue.addEventListener("click", async () => {
    birthdayContinue.disabled = true;
    try {
        const { response, data } = await requestJson("/api/users/birthday/ack", {
            method: "POST",
            body: "{}",
            authToken: userToken
        });
        if (!response.ok || !data.ok) throw new Error(data.message || "无法确认生日祝福。");
        nextDestination = "main";
        birthdayGate.hidden = true;
        mainContent.hidden = false;
    } catch (error) {
        birthdayMessage.textContent = error.message || "暂时无法开启书页，请重试。";
    } finally {
        birthdayContinue.disabled = false;
    }
});

switchUserButton.addEventListener("click", () => {
    saveUserToken("");
    nextDestination = "onboarding";
    setProfileForm("return");
    recoveryStage.hidden = true;
    profileForms.hidden = false;
    revealDestination();
});

function clearError() {
    errorMessage.hidden = true;
    errorMessage.textContent = "";
}

function setLoading(isLoading) {
    requestInProgress = isLoading;
    askButton.disabled = isLoading;
    buttonText.textContent = isLoading ? "星海正在回应……" : "揭晓命运的答案";
}

function wait(milliseconds) {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function revealEasterEggAnswer(eggId, title) {
    if (reducedMotion.matches || !fateGateReveal) {
        answerPanel.hidden = false;
        answerPanel.classList.add("is-effect-active");
        launchEggParticles(eggId);
        return;
    }

    fateGateReveal.dataset.eggId = eggId;
    fateGateReveal.classList.toggle("is-gate-scene", eggId === "fate-gate");
    eggRevealTitle.textContent = title;
    fateGateReveal.hidden = false;
    fateGateReveal.classList.remove("is-opening", "is-leaving", "is-active");
    void fateGateReveal.offsetWidth;
    fateGateReveal.classList.add("is-active");
    await wait(720);
    fateGateReveal.classList.add("is-opening");
    await wait(1750);
    answerPanel.hidden = false;
    answerPanel.classList.add("is-effect-active");
    await wait(250);
    fateGateReveal.classList.add("is-leaving");
    await wait(650);
    fateGateReveal.hidden = true;
    fateGateReveal.classList.remove("is-active", "is-opening", "is-leaving");
    fateGateReveal.classList.remove("is-gate-scene");
    delete fateGateReveal.dataset.eggId;
    launchEggParticles(eggId);
}

async function askQuestion() {
    if (requestInProgress) return;
    clearError();
    const question = questionInput.value.trim();

    if (!question) {
        errorMessage.textContent = "请先写下你真正想问的问题。";
        errorMessage.hidden = false;
        questionInput.focus();
        return;
    }

    latestQuestion = question;
    reviewStatus.hidden = true;
    reviewStatus.textContent = "";
    answerPanel.hidden = true;
    answerPanel.classList.remove("is-effect-active");
    stopEggParticles();
    bookObject.classList.remove("has-answer", "is-turning");
    bookObject.classList.add("is-open", "is-opening", "is-thinking");
    bookStage.classList.add("is-thinking");
    bookCover.classList.add("is-opening");
    pageWaiting.hidden = false;
    setLoading(true);
    playSceneSound("open");

    try {
        const { response, data } = await requestJson("/api/answer", {
            method: "POST",
            body: JSON.stringify({ question }),
            authToken: userToken
        });
        if (!response.ok || !data.ok) {
            throw new Error(data.message || "暂时无法取得答案，请稍后再试。");
        }

        await wait(reducedMotion.matches ? 0 : 450);
        answerText.textContent = data.answer;
        answerCategory.textContent = data.is_easter_egg
            ? data.category
            : `THE BOOK HAS SPOKEN · ${data.category}`;
        answerNote.textContent = data.egg_discovered
            ? "这条星海秘语已记入你的探索记录。继续探索，也记得由自己作出选择。"
            : data.is_easter_egg
                ? "你再次遇见了一条隐藏讯息。继续探索，也记得由自己作出选择。"
            : "请把它当作一次思考的提示，而不是不可更改的预言。";

        bookObject.classList.remove("is-thinking");
        bookStage.classList.remove("is-thinking");
        bookObject.classList.add("has-answer", "is-turning");
        playSceneSound("flip");
        pageWaiting.hidden = true;
        answerPanel.classList.toggle("is-rare", Boolean(data.is_easter_egg));
        answerPanel.classList.toggle("is-epic", data.egg_tier === "epic");
        answerPanel.classList.toggle(
            "is-common-egg",
            data.is_easter_egg && data.egg_tier === "common"
        );
        answerPanel.classList.toggle(
            "is-gate-egg",
            data.is_easter_egg && data.effect === "golden-gate"
        );
        answerPanel.dataset.effect = data.effect || "answer";
        answerPanel.dataset.eggId = data.egg_id || "";
        bookObject.dataset.effect = data.effect || "answer";
        bookObject.classList.remove("is-effect-active");
        reviewQuestionButton.hidden = ["exact", "approved-special"].includes(data.priority);
        const isCinematicEgg = data.is_easter_egg;
        answerPanel.hidden = isCinematicEgg;
        if (data.is_easter_egg) {
            window.requestAnimationFrame(() => {
                bookObject.classList.add("is-effect-active");
            });
        }
        playSceneSound(data.sound || (data.is_easter_egg ? "rare" : "answer"));

        if (isCinematicEgg) {
            await revealEasterEggAnswer(data.egg_id, data.category);
        } else {
            await wait(reducedMotion.matches ? 0 : 920);
        }
        bookObject.classList.remove("is-turning", "is-opening");
        window.setTimeout(() => {
            bookObject.scrollIntoView({
                behavior: reducedMotion.matches ? "auto" : "smooth",
                block: "center"
            });
        }, 80);
    } catch (error) {
        errorMessage.textContent = error.message || "连接失败，请确认 Flask 服务仍在运行。";
        errorMessage.hidden = false;
        bookObject.classList.remove("is-thinking", "is-turning", "is-opening");
        bookStage.classList.remove("is-thinking");
        pageWaiting.hidden = true;
    } finally {
        setLoading(false);
        bookCover.classList.remove("is-opening");
    }
}

askButton.addEventListener("click", askQuestion);
questionInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        askQuestion();
    }
});

askAgainButton.addEventListener("click", () => {
    answerPanel.hidden = true;
    answerPanel.classList.remove("is-rare", "is-epic", "is-common-egg");
    answerPanel.classList.remove("is-gate-egg");
    delete answerPanel.dataset.eggId;
    stopEggParticles();
    answerPanel.classList.remove("is-effect-active");
    delete answerPanel.dataset.effect;
    reviewQuestionButton.hidden = false;
    reviewStatus.hidden = true;
    reviewStatus.textContent = "";
    bookObject.classList.remove(
        "is-open", "is-opening", "is-thinking", "is-turning", "has-answer",
        "is-effect-active"
    );
    delete bookObject.dataset.effect;
    bookStage.classList.remove("is-thinking");
    pageWaiting.hidden = true;
    questionInput.value = "";
    updateCharCount();
    questionInput.focus();
    window.scrollTo({ top: 0, behavior: reducedMotion.matches ? "auto" : "smooth" });
});

reviewQuestionButton.addEventListener("click", async () => {
    if (!latestQuestion || !userToken) return;
    reviewQuestionButton.disabled = true;
    reviewStatus.hidden = true;
    try {
        const { response, data } = await requestJson("/api/special-questions", {
            method: "POST",
            body: JSON.stringify({ question: latestQuestion }),
            authToken: userToken
        });
        if (response.status === 409 && data.message.includes("提交过")) {
            reviewStatus.textContent = data.message;
        } else if (!response.ok || !data.ok) {
            throw new Error(data.message || "审核申请提交失败。");
        } else {
            reviewStatus.textContent = `${data.message} 申请编号：${data.request_id}`;
        }
        reviewStatus.hidden = false;
    } catch (error) {
        reviewStatus.textContent = error.message || "审核申请暂时无法提交。";
        reviewStatus.hidden = false;
    } finally {
        reviewQuestionButton.disabled = false;
    }
});

soundButton.addEventListener("click", () => {
    soundEnabled = !soundEnabled;
    saveSetting("answerBookSound", soundEnabled ? "on" : "off");
    updateSoundButton();
    if (soundEnabled) {
        audioUnlocked = true;
        startAmbient();
        playSceneSound("answer");
    } else {
        stopScheduledSound();
        stopAmbient(true);
        if (audioContext && audioContext.state === "running") {
            audioContext.suspend().catch(() => {});
        }
    }
});

document.addEventListener("click", (event) => {
    if (!soundEnabled || !(event.target instanceof Element)) return;
    const button = event.target.closest("button");
    if (!button || ["askButton", "soundButton", "skipOpening", "birthdayContinue", "recoveryContinue"].includes(button.id)) {
        return;
    }
    playSceneSound("click");
});

function finishOpening() {
    if (!document.body.classList.contains("opening-active")) return;
    window.clearTimeout(openingTimer);
    opening.classList.add("is-leaving");
    window.setTimeout(() => {
        document.body.classList.remove("opening-active");
        document.body.classList.add("opening-seen");
        saveSetting("answerBookIntroSeen", "yes");
        revealDestination();
    }, reducedMotion.matches ? 0 : 760);
}

skipOpeningButton.addEventListener("click", finishOpening);

function unlockAudioPlayback() {
    if (!soundEnabled) return;
    audioUnlocked = true;
    if (!getAudioContext()) return;
    startAmbient();
    if (document.body.classList.contains("opening-active") && !openingSoundPlayed) {
        openingSoundPlayed = true;
        playSceneSound("opening");
    }
}
document.addEventListener("pointerdown", unlockAudioPlayback);
document.addEventListener("keydown", unlockAudioPlayback);

function startOpening() {
    const alreadySeen = readSetting("answerBookIntroSeen") === "yes";
    if (alreadySeen || reducedMotion.matches) {
        document.body.classList.add("opening-seen");
        revealDestination();
        return;
    }

    document.body.classList.add("opening-active");
    if (!reducedMotion.matches) {
        animationFrame = window.requestAnimationFrame(drawStars);
    }
    openingTimer = window.setTimeout(finishOpening, 6900);
    skipOpeningButton.focus({ preventScroll: true });
}

function resizeStarCanvas() {
    if (!openingStars) return;
    const rect = openingStars.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
    openingStars.width = Math.round(rect.width * ratio);
    openingStars.height = Math.round(rect.height * ratio);
    const context = openingStars.getContext("2d");
    if (!context) return;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);

    const count = reducedMotion.matches
        ? 0
        : Math.min(105, Math.max(34, Math.round(rect.width / 9)));
    starParticles = Array.from({ length: count }, () => ({
        x: Math.random() * rect.width,
        y: Math.random() * rect.height,
        radius: Math.random() * 1.25 + 0.25,
        alpha: Math.random() * 0.64 + 0.2,
        drift: Math.random() * 0.18 + 0.025
    }));
    drawStars();
}

function drawStars() {
    const context = openingStars && openingStars.getContext("2d");
    if (!context) return;
    const width = openingStars.clientWidth;
    const height = openingStars.clientHeight;
    context.clearRect(0, 0, width, height);
    starParticles.forEach((star) => {
        context.beginPath();
        context.fillStyle = `rgba(236, 230, 255, ${star.alpha})`;
        context.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
        context.fill();
        if (!reducedMotion.matches && !document.hidden) {
            star.y -= star.drift;
            star.alpha += (Math.random() - 0.5) * 0.012;
            star.alpha = Math.min(.9, Math.max(.16, star.alpha));
            if (star.y < 0) {
                star.y = height;
                star.x = Math.random() * width;
            }
        }
    });

    if (
        !reducedMotion.matches &&
        !document.hidden &&
        document.body.classList.contains("opening-active")
    ) {
        animationFrame = window.requestAnimationFrame(drawStars);
    } else {
        animationFrame = null;
    }
}

document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopEggParticles();
    if (document.hidden && animationFrame !== null) {
        window.cancelAnimationFrame(animationFrame);
        animationFrame = null;
    }
    if (document.hidden) {
        stopAmbient(true);
    } else if (audioUnlocked && soundEnabled) {
        startAmbient();
    }
    if (
        !document.hidden &&
        animationFrame === null &&
        !reducedMotion.matches &&
        document.body.classList.contains("opening-active")
    ) {
        animationFrame = window.requestAnimationFrame(drawStars);
    }
});
window.addEventListener("resize", resizeStarCanvas);
reducedMotion.addEventListener("change", resizeStarCanvas);

updateCharCount();
resizeStarCanvas();
startOpening();
initializeProfile();
