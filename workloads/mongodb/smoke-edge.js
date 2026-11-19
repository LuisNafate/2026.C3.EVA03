// Se concatena después de consultas.js. La colección de prueba es desechable.
function decimalText(value) {
  return String(value).replace(/^NumberDecimal\("(.+)"\)$/, "$1");
}

function evidence(label, value) {
  print("EDGE_" + label + " " + JSON.stringify(value));
}

if (stage === "insert") {
  var documents = cat(datasetPath).trim().split("\n").map(JSON.parse);
  documents.forEach(function (document) {
    document.items.forEach(function (item) {
      item.price = NumberDecimal(item.price.toFixed(2));
    });
    document.payment.final_total = NumberDecimal(document.payment.final_total.toFixed(2));
  });
  assert.commandWorked(db.runCommand({ insert: "orders", documents: documents, ordered: true }));
}

evidence("META", { phase: stage, documents: db.orders.countDocuments({}), version: db.version() });
evidence("Q1", db.orders.aggregate(q1, { collation: { locale: "simple" } }).toArray().map(function (row) {
  return [row._id.country, row._id.category, decimalText(row.sum_subtotal),
          decimalText(row.avg_subtotal), Number(row.items)];
}));
evidence("Q2", db.orders.aggregate(q2, { collation: { locale: "simple" } }).toArray().map(function (row) {
  return [row.order_id, decimalText(row.final_total)];
}));
