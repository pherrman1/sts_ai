//
// Created by gamerpuppy on 7/4/2021.
//

#ifndef STS_LIGHTSPEED_ACTIONQUEUE_H
#define STS_LIGHTSPEED_ACTIONQUEUE_H

#include "sts_common.h"
#include "combat/Actions.h"

#include <bitset>
#include <array>
#include <cassert>


namespace sts {

    // Simple deque
    template<int capacity>
    struct ActionQueue {
        friend BattleContext;
        int front = 0;
        int back = 0;
        int size = 0;
        std::bitset<capacity> bits; // for the shouldClear field
        std::bitset<capacity> postVictoryBits;

#ifdef sts_action_queue_use_raw_array
        Action arr[capacity];
        ActionQueue() = default;
        ActionQueue(const ActionQueue &rhs)
            : size(rhs.size), back(rhs.back), front(rhs.front), bits(rhs.bits),
              postVictoryBits(rhs.postVictoryBits) {
            int cur = rhs.front;
            for (int i = 0; i < rhs.size; ++i) {
                if (cur >= capacity) {
                    cur = 0;
                }
                arr[cur] = rhs.arr[cur];
            }
        }
#else
        std::array<Action,capacity> arr;
#endif

        void clear();
        void pushFront(Action a);
        void pushBack(Action a);
        bool isEmpty();
        bool hasPostVictoryAction() const;
        Action popPostVictoryAction();
        Action popFront();
        [[nodiscard]] int getCapacity() const;

        // Compares the queued actions in order (each carries its own victory
        // flags); ring slots outside the queue are ignored.
        bool operator==(const ActionQueue &rhs) const {
            if (size != rhs.size) {
                return false;
            }
            for (int i = 0; i < size; ++i) {
                if (!(arr[(front + i) % capacity] == rhs.arr[(rhs.front + i) % capacity])) {
                    return false;
                }
            }
            return true;
        }
    };

    template<int capacity>
    void ActionQueue<capacity>::clear() {
        size = 0;
        back = 0;
        front = 0;
        bits.reset();
        postVictoryBits.reset();
    }

    template <int capacity>
    void ActionQueue<capacity>::pushFront(Action a) {
#ifdef sts_asserts
        assert(size != capacity);
#endif
        --front;
        ++size;
        if (front < 0) {
            front = capacity-1;
        }
        bits.set(front, a.clearOnCombatVictory);
        postVictoryBits.set(front, a.executeAfterCombatVictory);
        arr[front] = a;
    }

    template<int capacity>
    void ActionQueue<capacity>::pushBack(Action a) {
#ifdef sts_asserts
        if (size >= capacity) {
            assert(false);
        }
#endif
        if (back >= capacity) {
            back = 0;
        }
        bits.set(back, a.clearOnCombatVictory);
        postVictoryBits.set(back, a.executeAfterCombatVictory);
        arr[back] = a;
        ++back;
        ++size;
    }

    template<int capacity>
    bool ActionQueue<capacity>::isEmpty() {
        return size == 0;
    }

    template<int capacity>
    bool ActionQueue<capacity>::hasPostVictoryAction() const {
        int cur = front;
        for (int i = 0; i < size; ++i) {
            if (cur >= capacity) {
                cur = 0;
            }
            if (postVictoryBits[cur]) {
                return true;
            }
            ++cur;
        }
        return false;
    }

    template<int capacity>
    Action ActionQueue<capacity>::popPostVictoryAction() {
        int cur = front;
        for (int i = 0; i < size; ++i) {
            if (cur >= capacity) {
                cur = 0;
            }
            if (postVictoryBits[cur]) {
                Action a = arr[cur];
                clear();
                return a;
            }
            ++cur;
        }
        return {};
    }

    template<int capacity>
    Action ActionQueue<capacity>::popFront() {
#ifdef sts_asserts
        assert(size > 0 );
#endif
        Action a = arr[front];
        ++front;
        --size;
        if (front >= capacity) {
            front = 0;
        }
        return a;
    }

    template<int capacity>
    int ActionQueue<capacity>::getCapacity() const {
        return capacity;
    }

}


#endif //STS_LIGHTSPEED_ACTIONQUEUE_H
