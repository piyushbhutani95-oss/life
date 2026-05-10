// Shared data for both versions

const HABITS = [
  // Morning
  { id: 'wake', name: 'Wake up early', time: 'morning', duration: null, durLabel: '', priority: 'high', category: 'health', streak: [1,1,1,0,1,1,1,1,0,1,1,1,1,0], done: false, hour: 6 },
  { id: 'bath', name: 'Bath', time: 'morning', duration: 10, durLabel: '10m', priority: null, category: 'health', streak: [1,1,1,1,1,0,1,1,1,1,1,0,1,1], done: false, hour: 7 },
  { id: 'skin', name: 'Skin care', time: 'morning', duration: 5, durLabel: '5m', priority: null, category: 'health', streak: [1,0,1,1,0,1,1,1,1,0,1,1,1,1], done: false, hour: 7 },
  { id: 'multi', name: 'Multivitamins', time: 'morning', duration: 1, durLabel: '1m', priority: null, category: 'health', streak: [1,1,1,1,1,1,1,1,1,0,1,1,1,1], done: false, hour: 8 },
  { id: 'b12', name: 'B12', time: 'morning', duration: 1, durLabel: '1m', priority: null, category: 'health', streak: [1,1,1,1,1,1,0,1,1,1,1,1,1,1], done: false, hour: 8 },
  { id: 'creatine', name: 'Creatine', time: 'morning', duration: 1, durLabel: '1m', priority: null, category: 'health', streak: [1,1,1,1,0,1,1,1,1,1,1,1,1,1], done: false, hour: 8 },
  { id: 'meditate', name: 'Meditate', time: 'morning', duration: 15, durLabel: '15m', priority: null, category: 'mind', streak: [1,1,0,1,1,1,1,0,1,1,1,1,0,1], done: false, hour: 8 },
  { id: 'write', name: 'Write', time: 'morning', duration: 60, durLabel: '1h', priority: 'high', category: 'mind', streak: [1,1,1,0,1,1,1,1,1,0,1,1,1,1], done: false, hour: 9 },

  // Afternoon
  { id: 'workout', name: 'Workout', time: 'afternoon', duration: 45, durLabel: '45m', priority: 'high', category: 'health', streak: [1,0,1,1,1,0,1,1,0,1,1,1,1,0], done: false, hour: 13 },
  { id: 'step', name: 'Step out', time: 'afternoon', duration: 15, durLabel: '15m', priority: null, category: 'health', streak: [1,1,1,1,0,1,1,1,1,1,0,1,1,1], done: false, hour: 14 },
  { id: 'code', name: 'Code', time: 'afternoon', duration: 90, durLabel: '1h 30m', priority: 'high', category: 'skills', streak: [1,1,1,1,1,1,1,1,1,1,1,1,1,0], done: false, hour: 15 },
  { id: 'guitar', name: 'Practice guitar', time: 'afternoon', duration: 30, durLabel: '30m', priority: null, category: 'skills', streak: [0,1,1,0,1,1,0,1,1,0,1,1,0,1], done: false, hour: 16 },
  { id: 'language', name: 'Language', time: 'afternoon', duration: 20, durLabel: '20m', priority: null, category: 'skills', streak: [1,1,0,1,1,1,1,1,0,1,1,1,1,1], done: false, hour: 17 },
  { id: 'course', name: 'Course', time: 'afternoon', duration: 30, durLabel: '30m', priority: null, category: 'skills', streak: [1,1,1,0,1,1,1,1,1,1,0,1,1,1], done: false, hour: 17 },

  // Evening
  { id: 'journal', name: 'Journal', time: 'evening', duration: 15, durLabel: '15m', priority: null, category: 'mind', streak: [1,1,1,1,1,0,1,1,1,1,1,1,0,1], done: false, hour: 20 },
  { id: 'read', name: 'Read', time: 'evening', duration: 30, durLabel: '30m', priority: 'high', category: 'mind', streak: [1,1,1,1,1,1,1,1,0,1,1,1,1,1], done: false, hour: 21 },
  { id: 'talk', name: 'Talk to people', time: 'evening', duration: null, durLabel: '', priority: null, category: 'social', streak: [1,0,1,1,0,1,1,1,0,1,1,0,1,1], done: false, hour: 19 },
  { id: 'respond', name: 'Respond to people', time: 'evening', duration: null, durLabel: '', priority: null, category: 'social', streak: [1,1,1,1,1,0,1,1,1,1,1,1,1,1], done: false, hour: 20 },
];

const CATEGORIES = [
  { id: 'all', label: 'All', count: HABITS.length },
  { id: 'health', label: 'Health', count: HABITS.filter(h => h.category === 'health').length },
  { id: 'mind', label: 'Mind', count: HABITS.filter(h => h.category === 'mind').length },
  { id: 'skills', label: 'Skills', count: HABITS.filter(h => h.category === 'skills').length },
  { id: 'social', label: 'Social', count: HABITS.filter(h => h.category === 'social').length },
];

window.HABITS = HABITS;
window.CATEGORIES = CATEGORIES;
