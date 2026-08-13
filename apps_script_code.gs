/**
 * ============================================================
 *  Project Perbaikan - Google Apps Script (Web App)
 *  Fungsi: menerima data dari app Streamlit -> tulis ke sheet
 * ============================================================
 *  CARA SETUP (sekali saja):
 *  1. Buka Google Sheet-nya di browser
 *  2. Menu: Extensions (Ekstensi) -> Apps Script
 *  3. Hapus semua kode default, paste SEMUA kode ini
 *  4. Tekan Ctrl+S untuk save (PENTING!)
 *  5. Klik Deploy -> New deployment -> pilih type "Web app"
 *     - Execute as: Me
 *     - Who has access: Anyone
 *  6. Klik Deploy -> Review permissions -> pilih akun Google kamu
 *     -> Allow (izinkan akses SpreadsheetApp)
 *  7. Copy URL Web App (format: https://script.google.com/macros/s/XXXX/exec)
 *     -> kirim ke Nuh / masukkan di apps_script_config.json
 * ============================================================
 */

// ---- KONFIGURASI ----
var APP_TOKEN="pp-3051b019bc54b9c0";  // GANTI bebas, harus sama dengan di app
var SHEET_ID = "1Jvi7Ek8LynDr5dHdc0GBahqpwiKKv_v4d1u3l7RPZWw";
var SHEET_NAME = "Sheet1";              // Nama sheet tujuan

function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    var token = body.token || "";

    if (token !== APP_TOKEN) {
      return jsonReply({ ok: false, error: "Token salah. Cek APP_TOKEN di Apps Script & app." });
    }

    var values = body.values; // array 18 elemen (kolom A-R)
    if (!values || !Array.isArray(values) || values.length < 18) {
      return jsonReply({ ok: false, error: "Data tidak lengkap (harus 18 kolom)." });
    }

    var ss = SpreadsheetApp.openById(SHEET_ID);
    var sheet = ss.getSheetByName(SHEET_NAME);
    if (!sheet) {
      sheet = ss.getSheets()[0];
    }

    // Cek duplikat: kunci = Surat (D, kolom 4) + Nomor Aju (J, kolom 10)
    // Satu nomor aju bisa dapat beberapa surat persetujuan, jadi aju saja TIDAK cukup.
    var dupLast = sheet.getLastRow();
    if (dupLast >= 2) {
      var scan = sheet.getRange(2, 1, dupLast - 1, 10).getValues();
      var key = String(values[3]) + "|" + String(values[9]);
      for (var i = 0; i < scan.length; i++) {
        if (String(scan[i][3]) + "|" + String(scan[i][9]) === key) {
          return jsonReply({ ok: true, duplicate: true, row: i + 2,
                             message: "Duplikat — sudah ada di baris " + (i + 2) });
        }
      }
    }

    // Isi kolom A (No) otomatis = nilai maksimum kolom A + 1
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
    values[0] = no; // set No

    sheet.appendRow(values);

    return jsonReply({ ok: true, row: no, message: "Tersimpan ke baris " + no });
  } catch (err) {
    return jsonReply({ ok: false, error: String(err) });
  }
}

function doGet() {
  return jsonReply({ ok: true, message: "Project Perbaikan web app aktif" });
}

function jsonReply(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
