/*
 * Firebase Cloud Messaging service worker for Switch.
 *
 * Served at /app/static/firebase-messaging-sw.js by Streamlit's static
 * file serving (the project's static/ folder is mapped to /app/static/).
 * It is registered explicitly by static/fcm.html with the public
 * Firebase web config carried in the query string -- no build step and
 * no hard-coded per-deployment values in this file.
 *
 * Messages are sent data-only (see fcm_client._message_payload) and
 * shown here. That is deliberate: a `notification` payload would be
 * auto-displayed by the FCM SDK in addition to this handler, producing
 * duplicates, and would not let us use the ad's large image exactly the
 * way the dashboard previews it.
 */
importScripts("https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js");

var DEFAULT_ICON = "/app/static/icons/switch-192.png";
var DEFAULT_BADGE = "/app/static/icons/switch-96.png";

function decodeBase64Url(raw) {
  var value = String(raw || "").replace(/-/g, "+").replace(/_/g, "/");
  while (value.length % 4) value += "=";
  var binary = atob(value);
  var bytes = new Uint8Array(binary.length);
  for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

var params = new URL(self.location.href).searchParams;
var firebaseConfig = null;
try {
  firebaseConfig = JSON.parse(decodeBase64Url(params.get("config")));
} catch (error) {
  // A malformed/missing config means the page that registered this
  // worker passed nothing useful; leave it registered but inert rather
  // than throwing on every push event.
  firebaseConfig = null;
}

if (firebaseConfig && firebaseConfig.messagingSenderId) {
  firebase.initializeApp(firebaseConfig);
  var messaging = firebase.messaging();

  messaging.onBackgroundMessage(function (payload) {
    var data = (payload && payload.data) || {};
    showAdNotification(data);
  });
}

// Activate a new worker immediately and take control of clients inside
// this worker's /app/static/ scope (the fcm.html iframe). Without
// clients.claim(), that iframe would stay uncontrolled until its next
// reload, which delays foreground message handling.
self.addEventListener("install", function () {
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});

function showAdNotification(data) {
  var title = data.title || "Switch";
  var options = {
    body: data.body || "",
    icon: data.icon || DEFAULT_ICON,
    badge: DEFAULT_BADGE,
    tag: "switch-ad",
    renotify: true,
    data: { click_url: data.click_url || "/" },
  };
  if (data.image) options.image = data.image;

  return self.registration.showNotification(title, options);
}

function targetUrl(clickUrl, clientUrl) {
  try {
    var target = new URL(clickUrl || "/", self.location.origin);
    // Streamlit keeps the signed-in session in ?session=. A tap on "/"
    // would otherwise drop it and send the student back to sign-in even
    // though this browser was already logged in. Carry it over for
    // same-origin targets; never leak it to an external URL.
    if (clientUrl) {
      var current = new URL(clientUrl);
      var session = current.searchParams.get("session");
      if (session && target.origin === current.origin && !target.searchParams.get("session")) {
        target.searchParams.set("session", session);
      }
    }
    return target.href;
  } catch (error) {
    return self.location.origin + "/";
  }
}

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  var clickUrl = event.notification.data && event.notification.data.click_url;

  event.waitUntil(
    (async function () {
      var allClients = await clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      for (var i = 0; i < allClients.length; i++) {
        var client = allClients[i];
        try {
          if (new URL(client.url).origin !== self.location.origin) continue;
        } catch (error) {
          continue;
        }
        // The hidden opt-in/runtime iframe is same-origin but is not the
        // app UI; never focus or navigate it instead of the real page.
        if (client.url.indexOf("/app/static/fcm.html") !== -1) continue;
        var url = targetUrl(clickUrl, client.url);
        var navigated = false;
        try {
          await client.focus();
          if ("navigate" in client) {
            await client.navigate(url);
            navigated = true;
          }
        } catch (error) {
          // Some browsers refuse navigate() on a client that is not
          // controlled by this worker (Streamlit's top-level page is
          // outside its /app/static/ scope). Fall through to a new
          // window rather than silently doing nothing.
        }
        if (navigated) return;
        await clients.openWindow(url);
        return;
      }
      await clients.openWindow(targetUrl(clickUrl, null));
    })()
  );
});
