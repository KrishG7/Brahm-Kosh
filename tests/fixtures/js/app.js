// Express-style API example for testing brahm-kosh JS adapter

async function fetchUser(id) {
    if (!id) return null;
    const res = await fetch(`/api/users/${id}`);
    if (!res.ok) throw new Error('Not found');
    return await res.json();
}

const processData = (data) => {
    return data.filter(x => x.active).map(x => ({
        ...x,
        score: computeScore(x),
    }));
};

class UserService {
    constructor(db) {
        this.db = db;
    }

    async getUser(id) {
        const user = await this.db.find(id);
        if (!user) throw new Error('Not found');
        return user;
    }

    async updateUser(id, data) {
        if (!id || !data) return null;
        for (const key of Object.keys(data)) {
            if (key === 'password') {
                data[key] = hashPassword(data[key]);
            }
        }
        return await this.db.update(id, data);
    }
}

module.exports = { UserService, fetchUser, processData };
