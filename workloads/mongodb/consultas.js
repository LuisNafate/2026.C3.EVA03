// Referencia para mongosh. No ejecutada en la Raspberry Pi.
// Importar el mismo JSONL. Normalizar sumas y promedios a dos decimales
// con redondeo de mitades hacia arriba en el cliente al cotejar Q1.
const q1 = [
  { $unwind: "$items" },
  { $match: { "items.price": { $gt: 50 } } },
  { $set: { subtotal: { $multiply: ["$items.qty", { $toDecimal: "$items.price" }] } } },
  { $group: {
    _id: { country: "$customer.country", category: "$items.category" },
    sum_subtotal: { $sum: "$subtotal" },
    avg_subtotal: { $avg: "$subtotal" },
    items: { $sum: 1 },
  } },
  { $sort: { "_id.country": 1, "_id.category": 1 } },
];

const q2 = [
  { $match: { status: "completed", timestamp: { $gte: "2025-03-01", $lt: "2025-12-01" } } },
  { $set: { final_total: { $toDecimal: "$payment.final_total" } } },
  { $sort: { final_total: -1, order_id: 1 } },
  { $limit: 1000 },
  { $project: { _id: 0, order_id: 1, final_total: 1 } },
];

// Usar la colación "simple" al ejecutar db.orders.aggregate(q1) o aggregate(q2).
