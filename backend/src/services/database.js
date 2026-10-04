/** MongoDB removed — persistence is via Supabase (Python API). */

module.exports = {
  connectDB: async () => true,
  getUsersCollection: () => null,
  getCreditsCollection: () => null,
  getTransactionsCollection: () => null,
  getFarmsCollection: () => null,
};
