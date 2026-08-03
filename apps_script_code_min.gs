var APP_TOKEN="pp-3051b019bc54b9c0";
var SHEET_ID = "1Jvi7Ek8LynDr5dHdc0GBahqpwiKKv_v4d1u3l7RPZWw";
var SHEET_NAME = "Sheet1";

function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    var token = body.token || "";
    if (token !== APP_TOKEN) {
      return jsonReply({ ok: false, error: "Token salah." });
    }
    var values = body.values;
    if (!values || !Array.isArray(values) || values.length < 18) {
      return jsonReply({ ok: false, error: "Data tidak lengkap." });
    }
    var ss = SpreadsheetApp.openById(SHEET_ID);
    var sheet = ss.getSheetByName(SHEET_NAME);
    if (!sheet) {
      sheet = ss.getSheets()[0];
    }
    var lastRow = sheet.getLastRow();
    var no = 1;
    if (lastRow >= 1) {
      var rangeA = sheet.getRange(2, 1, Math.max(lastRow - 1, 1), 1).getValues();
      var maxNo = 0;
      for (var i = 0; i < rangeA.length; i++) {
        var v = Number(rangeA[i][0]);
        if (!isNaN(v) && v > maxNo) maxNo = v;
      }
      no = maxNo + 1;
    }
    values[0] = no;
    sheet.appendRow(values);

    // Paksa kolom J (Nomor Aju) & L (Nopen) sebagai TEKS supaya
    // leading zero tidak hilang (misal 062388 -> 62388)
    var newRow = sheet.getLastRow();
    sheet.getRange(newRow, 10).setNumberFormat('@').setValue(String(values[9]));
    sheet.getRange(newRow, 12).setNumberFormat('@').setValue(String(values[11]));

    return jsonReply({ ok: true, row: no, message: "Baris " + no });
  } catch (err) {
    return jsonReply({ ok: false, error: String(err) });
  }
}

function doGet() {
  return jsonReply({ ok: true, message: "Project Perbaikan aktif" });
}

function jsonReply(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
