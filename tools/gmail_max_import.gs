/**
 * דוח האשראי — from Gmail straight into the app, once a day, for free.
 *
 * Google Apps Script (script.google.com) that finds the monthly Max statement
 * (transaction-details_export_*.xlsx) in this Gmail account, posts it to the
 * app's token-guarded import endpoint, labels the mail so it is never posted
 * twice, and mails a one-line summary with a link to the month's transactions.
 *
 * Setup (about five minutes):
 *   1. In the app's Railway service, add the variable IMPORT_TOKEN with a long
 *      random value, e.g. the output of:
 *        python -c "import secrets; print(secrets.token_urlsafe(48))"
 *      Redeploy. Without this variable the endpoint stays off (403).
 *   2. Open https://script.google.com with the Gmail account that receives the
 *      statement, create a new project and paste this file in.
 *   3. Project settings → Script properties → add two properties:
 *        APP_URL       https://<your-app-domain>     (no trailing slash)
 *        IMPORT_TOKEN  the same value as in Railway
 *   4. Run `importMaxStatements` once by hand and approve the Gmail and
 *      "connect to an external service" permissions it asks for.
 *   5. Triggers (the clock icon) → Add trigger → importMaxStatements,
 *      time-driven, day timer, e.g. 08:00–09:00. Done.
 *
 * Everything the app decides (which rows are new, whose card it is, the
 * category of each merchant) happens in the app; this script only carries
 * the file. Rows the app could not categorise are still added and counted in
 * the summary mail as "ללא קטגוריה", so they can be fixed on the transactions
 * page — one fix teaches the next statement.
 */

var LABEL_NAME = 'max-imported';
// The Max mail carries the statement as an xlsx attachment named
// transaction-details_export_<digits>.xlsx. Anything already labelled is skipped.
var GMAIL_QUERY = 'has:attachment filename:xlsx filename:transaction-details newer_than:60d -label:' + LABEL_NAME;

function importMaxStatements() {
  var props = PropertiesService.getScriptProperties();
  var appUrl = (props.getProperty('APP_URL') || '').replace(/\/+$/, '');
  var token = props.getProperty('IMPORT_TOKEN') || '';
  if (!appUrl || !token) {
    throw new Error('Set APP_URL and IMPORT_TOKEN in Project settings → Script properties.');
  }

  var label = GmailApp.getUserLabelByName(LABEL_NAME) || GmailApp.createLabel(LABEL_NAME);
  var threads = GmailApp.search(GMAIL_QUERY, 0, 20);
  var results = [];

  threads.forEach(function (thread) {
    var handled = false;
    thread.getMessages().forEach(function (message) {
      message.getAttachments({ includeInlineImages: false }).forEach(function (attachment) {
        if (!/^transaction-details.*\.xlsx$/i.test(attachment.getName())) return;
        var outcome = postStatement_(appUrl, token, attachment);
        outcome.file = attachment.getName();
        outcome.mailDate = message.getDate();
        results.push(outcome);
        handled = true;
      });
    });
    // Label even when the app rejected the file, so a broken mail is not retried daily;
    // the summary mail says what happened.
    if (handled) thread.addLabel(label);
  });

  if (results.length) sendSummary_(appUrl, results);
  Logger.log(JSON.stringify(results));
  return results;
}

/** POST one attachment to the app. Returns the parsed JSON, or {error: ...}. */
function postStatement_(appUrl, token, attachment) {
  var response = UrlFetchApp.fetch(appUrl + '/api/transactions/import/auto', {
    method: 'post',
    headers: { Authorization: 'Bearer ' + token },
    payload: { file: attachment.copyBlob().setName(attachment.getName()) },
    muteHttpExceptions: true,
  });
  var code = response.getResponseCode();
  var body = response.getContentText();
  try {
    var data = JSON.parse(body);
    if (code >= 200 && code < 300) return data;
    return { error: (data && data.detail) || ('HTTP ' + code) };
  } catch (e) {
    return { error: 'HTTP ' + code + ': ' + body.slice(0, 200) };
  }
}

/** One short mail per run, in Hebrew, with a link to the month's transactions. */
function sendSummary_(appUrl, results) {
  var lines = results.map(function (r) {
    if (r.error) return '✗ ' + r.file + ' — ' + r.error;
    var line = '✓ ' + (r.statement_month || r.file) + ': נוספו ' + r.added + ' עסקאות';
    var skipped = (r.skipped && (r.skipped.exists + r.skipped.recurring)) || 0;
    if (skipped) line += ', ' + skipped + ' כבר היו רשומות';
    if (r.unsorted) line += ', ' + r.unsorted + ' ללא קטגוריה';
    if (r.added && r.date_from && r.date_to) {
      line += '\n   ' + appUrl + '/finances/transactions?date_from=' + r.date_from + '&date_to=' + r.date_to;
    }
    return line;
  });
  MailApp.sendEmail({
    to: Session.getEffectiveUser().getEmail(),
    subject: 'דוח האשראי נטען לאפליקציה',
    body: lines.join('\n\n'),
  });
}
