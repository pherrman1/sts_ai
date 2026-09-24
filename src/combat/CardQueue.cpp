//
// Created by gamerpuppy on 8/24/2021.
//

#include "combat/CardQueue.h"
#include "sts_common.h"

#include <algorithm>

using namespace sts;


bool CardQueue::isEmpty() const {
    return size == 0;
}

bool CardQueue::containsCardWithId(int uniqueId) const {
    int idx = frontIdx;
    for (int i = 0; i < size; ++i) {
        if (frontIdx >= capacity) {
            idx = 0;
        }
        if (arr[idx].card.getUniqueId() == uniqueId) {
            return true;
        }
    }
    return false;
}

void CardQueue::clear() {
    size = 0;
    backIdx = 0;
    frontIdx = 0;
}

void CardQueue::pushFront(CardQueueItem item) {
#ifdef sts_asserts
    assert(size != arr.size());
#endif
    --frontIdx;
    ++size;
    if (frontIdx < 0) {
        frontIdx = capacity - 1;
    }
    arr.at(frontIdx) = std::move(item);
}

void CardQueue::pushBack(CardQueueItem item) {
#ifdef sts_asserts
    assert(size != capacity);
#endif
    arr.at(backIdx) = std::move(item);
    ++backIdx;
    ++size;
    if (backIdx >= capacity) {
        backIdx = 0;
    }
}

CardQueueItem CardQueue::popFront() {
#ifdef sts_asserts
    assert(size > 0);
#endif
    CardQueueItem &item = arr.at(frontIdx);
    ++frontIdx;
    --size;
    if (frontIdx >= capacity) {
        frontIdx = 0;
    }
    return item;
}

CardQueueItem CardQueue::popBack() {
#ifdef sts_asserts
    assert(size > 0);
#endif
    --backIdx;
    --size;
    if (backIdx < 0) {
        backIdx = arr.size() - 1;
    }
    CardQueueItem &item = arr.at(backIdx);
    return item;
}

CardQueueItem &CardQueue::front() {
#ifdef sts_asserts
    assert(size > 0);
#endif
    return arr.at(frontIdx);
}

bool CardQueue::operator==(const CardQueue &rhs) const {
    if (size != rhs.size) {
        return false;
    }
    for (int i = 0; i < size; ++i) {
        if (!(arr[(frontIdx + i) % capacity] == rhs.arr[(rhs.frontIdx + i) % capacity])) {
            return false;
        }
    }
    return true;
}
