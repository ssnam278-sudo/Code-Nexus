const CodeNexusAuth = (() => {
	let client;
	let session;
	let mode = 'signin';
	let magicLinkCooldown = false;
	const config = window.CODENEXUS_CONFIG || {};
	const configured = Boolean(config.supabaseUrl && config.supabaseAnonKey && window.supabase);
	const roles = ['Admin', 'District official', 'Field officer', 'Citizen'];

	function createClient() {
		if (configured) client = window.supabase.createClient(config.supabaseUrl, config.supabaseAnonKey);
	}

	function renderShell() {
		document.body.classList.add('auth-locked');
		const shell = document.createElement('div');
		shell.id = 'auth-shell';
		shell.innerHTML = `<div class="auth-card" role="dialog" aria-labelledby="auth-title">
			<aside class="auth-story"><div class="auth-story-brand"><span class="auth-mark">▲</span><strong>CODE NEXUS</strong></div><p class="auth-story-kicker">LANDSLIDE INTELLIGENCE NETWORK</p><div class="auth-signal"><span class="signal-orbit"></span><span class="signal-orbit"></span><span class="signal-core">●</span></div><div class="auth-story-copy"><p class="kicker">NORTH EASTERN REGION / 24·7 WATCH</p><h2>See risk earlier.<br><em>Act with clarity.</em></h2><p>One secure workspace for verified alerts, terrain intelligence, and ground observations.</p></div><div class="auth-story-foot"><span><i class="dot green"></i> Monitoring network online</span><span>v0.1 prototype</span></div></aside>
			<section class="auth-panel"><div class="auth-panel-top"><div class="auth-brand"><span class="auth-mark">▲</span><span>CODE NEXUS</span><small>FIELD INTELLIGENCE NETWORK</small></div><span class="auth-live"><i></i> SYSTEM ONLINE</span></div><div class="auth-heading"><p class="kicker">SECURE ACCESS / REGIONAL WATCH</p><span class="auth-step">01 <i></i> 02</span></div><h1 id="auth-title">Sign in to the situation room</h1><p id="auth-copy" class="auth-copy">Access alerts, zone intelligence, and field coordination tools.</p><button id="google-login" class="auth-google"><span>G</span> Continue with Google</button><div class="auth-divider"><span>or use email</span></div><form id="email-login" class="auth-form"><label id="name-field" class="auth-name-field">Full name<input id="auth-name" type="text" autocomplete="name" placeholder="Your name"></label><label>Email address<input id="auth-email" type="email" autocomplete="email" required placeholder="you@example.com"></label><label>Password<div class="password-field"><input id="auth-password" type="password" autocomplete="current-password" minlength="6" required placeholder="At least 6 characters"><button type="button" id="toggle-password" aria-label="Show password">Show</button></div></label><div class="auth-under-row"><label id="confirm-field" class="auth-confirm-field">Confirm password<div class="password-field"><input id="auth-confirm" type="password" autocomplete="new-password" minlength="6" placeholder="Repeat password"><button type="button" id="toggle-confirm" aria-label="Show password">Show</button></div></label><button type="button" class="auth-link auth-forgot" id="forgot-login">Forgot password?</button></div><div class="auth-actions"><button type="submit" id="submit-auth" data-auth-action="signin">Sign in <span>→</span></button><button type="button" class="auth-link" id="magic-login">Email me a sign-in link</button></div></form><p id="auth-message" class="auth-message" role="status"></p><div class="auth-switch"><span id="switch-copy">New to Code Nexus?</span><button type="button" class="auth-link" id="switch-auth">Create an account <span>→</span></button></div><small class="auth-demo-note">Protected access for authorised response teams.</small></section>
		</div>`;
		document.body.prepend(shell);
		shell.querySelectorAll('.auth-story-brand strong, .auth-brand span:not(.auth-mark)').forEach(element => { element.textContent = 'CODE NEXUS'; });
		$('google-login').addEventListener('click', signInWithGoogle);
		$('email-login').addEventListener('submit', signInWithEmail);
		$('magic-login').addEventListener('click', sendMagicLink);
		$('forgot-login').addEventListener('click', resetPassword);
		$('switch-auth').addEventListener('click', toggleMode);
		$('toggle-password').addEventListener('click', () => togglePassword('auth-password', 'toggle-password'));
		$('toggle-confirm').addEventListener('click', () => togglePassword('auth-confirm', 'toggle-confirm'));
		updateMode();
	}

	function $(id) { return document.getElementById(id); }
	function message(text, error = false) { const element = $('auth-message'); element.textContent = text; element.classList.toggle('error', error); }
	function callbackUrl() { return `${window.location.origin}${window.location.pathname}`; }
	function setVisible(visible) { const shell = $('auth-shell'); shell.classList.toggle('hidden', !visible); shell.hidden = !visible; shell.style.display = visible ? 'grid' : 'none'; document.body.classList.toggle('auth-locked', visible); }
	function setDemoMode() { setVisible(false); addUserBadge('Demo mode'); document.dispatchEvent(new CustomEvent('codenexus:authenticated', { detail: { role:'Demo operator' } })); }
	function updateMode() { const signup = mode === 'signup'; $('auth-title').textContent = signup ? 'Create your field account' : 'Sign in to the situation room'; $('auth-copy').textContent = signup ? 'Join the network to submit observations and follow verified alerts.' : 'Access alerts, zone intelligence, and field coordination tools.'; $('submit-auth').innerHTML = signup ? 'Create account <span>→</span>' : 'Sign in <span>→</span>'; $('switch-copy').textContent = signup ? 'Already have an account?' : 'New to Code Nexus?'; $('switch-auth').innerHTML = signup ? 'Sign in <span>→</span>' : 'Create an account <span>→</span>'; $('name-field').hidden = !signup; $('confirm-field').hidden = !signup; $('name-field').style.display = signup ? 'block' : 'none'; $('confirm-field').style.display = signup ? 'block' : 'none'; $('forgot-login').hidden = signup; $('magic-login').hidden = signup; $('forgot-login').style.display = signup ? 'none' : 'block'; $('magic-login').style.display = signup ? 'none' : 'block'; $('auth-password').autocomplete = signup ? 'new-password' : 'current-password'; }
	function toggleMode() { mode = mode === 'signin' ? 'signup' : 'signin'; $('email-login').reset(); message(''); updateMode(); }
	function addUserBadge(label, user = null) {
		const deck = document.querySelector('.deck-status');
		if (!deck || document.getElementById('auth-user-badge')) return;
		const badge = document.createElement('span');
		badge.id = 'auth-user-badge';
		badge.className = 'auth-user-badge';
		badge.innerHTML = `<button id="profile-toggle" class="profile-toggle" aria-expanded="false"><i class="dot cyan"></i><span class="profile-label"></span><b>⌄</b></button><div id="profile-menu" class="profile-menu"><strong class="profile-name"></strong><small class="profile-email"></small><span class="profile-role"></span><button id="auth-logout" class="profile-logout">Sign out <span>↪</span></button></div>`;
		badge.querySelector('.profile-label').textContent = label;
		badge.querySelector('.profile-name').textContent = user?.user_metadata?.full_name || user?.user_metadata?.name || label;
		badge.querySelector('.profile-email').textContent = user?.email || '';
		badge.querySelector('.profile-role').textContent = `Role: ${label}`;
		deck.prepend(badge);
		$('profile-toggle').addEventListener('click', () => { const open = badge.classList.toggle('open'); $('profile-toggle').setAttribute('aria-expanded', String(open)); });
		$('auth-logout').addEventListener('click', signOut);
	}
	async function signInWithGoogle() { if (!client) return message('Google sign-in is unavailable in local demo mode.', true); message('Opening Google sign-in...'); const { error } = await client.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: callbackUrl() } }); if (error) message(error.message, true); }
	function friendlyError(error) { if (!error) return ''; if (/rate limit|too many requests/i.test(error.message)) return 'Supabase has temporarily paused email delivery for this project. No new link was sent. Use Google sign-in, or wait for the limit to reset and try once later.'; if (/invalid login credentials/i.test(error.message)) return 'That email and password do not match. If you used Google, choose Continue with Google instead. To use email sign-in, create an account with a password first.'; if (/email not confirmed/i.test(error.message)) return 'Please confirm your email address before signing in.'; return error.message; }
	async function signInWithEmail(event) { event.preventDefault(); const email = $('auth-email').value; const password = $('auth-password').value; if (mode === 'signup') { if ($('auth-password').value !== $('auth-confirm').value) return message('Passwords do not match.', true); const { data, error } = await client.auth.signUp({ email, password, options: { data: { full_name: $('auth-name').value.trim() }, emailRedirectTo: callbackUrl() } }); if (error) return message(friendlyError(error), true); message(data.session ? 'Account created. Opening your workspace...' : 'Account created. Check your email to confirm access.'); return; } const { error } = await client.auth.signInWithPassword({ email, password }); if (error) message(friendlyError(error), true); }
	async function sendMagicLink() { const email = $('auth-email').value; if (!email) return message('Enter your email address first.', true); if (magicLinkCooldown) return message('Please wait before requesting another sign-in email.', true); magicLinkCooldown = true; $('magic-login').disabled = true; $('magic-login').textContent = 'Checking email delivery...'; const { error } = await client.auth.signInWithOtp({ email, options: { emailRedirectTo: callbackUrl() } }); if (error) { message(friendlyError(error), true); $('magic-login').textContent = 'Email unavailable'; setTimeout(() => { magicLinkCooldown = false; $('magic-login').disabled = false; $('magic-login').textContent = 'Email me a sign-in link'; }, 60000); return; } message('Sign-in link sent. Open the newest email in your inbox and click the link to continue.'); $('magic-login').textContent = 'Email sent'; setTimeout(() => { magicLinkCooldown = false; $('magic-login').disabled = false; $('magic-login').textContent = 'Email me a sign-in link'; }, 60000); }
	async function resetPassword() { const email = $('auth-email').value; if (!email) return message('Enter your email address first.', true); const { error } = await client.auth.resetPasswordForEmail(email, { redirectTo: callbackUrl() }); message(error ? friendlyError(error) : 'Password reset instructions sent to your email.', Boolean(error)); }
	function togglePassword(inputId, buttonId) { const input = $(inputId); const visible = input.type === 'text'; input.type = visible ? 'password' : 'text'; $(buttonId).textContent = visible ? 'Show' : 'Hide'; }
	async function signOut() { if (client) await client.auth.signOut(); session = null; document.getElementById('auth-user-badge')?.remove(); if (configured) setVisible(true); }
	function applySession(nextSession) { session = nextSession; setVisible(!session); if (session) { const role = session.user.app_metadata?.role || session.user.user_metadata?.role || 'Citizen'; addUserBadge(role, session.user); document.dispatchEvent(new CustomEvent('codenexus:authenticated', { detail: { session, role } })); } }
	function init() { renderShell(); if (!configured) return setDemoMode(); createClient(); client.auth.getSession().then(({ data }) => applySession(data.session)); client.auth.onAuthStateChange((_event, nextSession) => applySession(nextSession)); }
	return { init, getSession: () => session, isConfigured: () => configured, roles };
})();

document.addEventListener('DOMContentLoaded', () => CodeNexusAuth.init());
