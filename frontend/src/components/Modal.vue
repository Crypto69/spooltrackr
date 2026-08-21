<script setup>
defineProps({ title: String, wide: Boolean })
const emit = defineEmits(['close'])
</script>
<template>
  <div class="modal-back" @click.self="emit('close')">
    <div class="modal" :class="{ wide }" role="dialog" :aria-label="title">
      <h3 v-if="title">{{ title }}</h3>
      <slot />
    </div>
  </div>
</template>
