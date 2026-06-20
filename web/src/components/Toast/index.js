import { createVNode, render } from 'vue'
import ToastComponent from './Index.vue'

// 动态创建根级 DOM 挂载支架
const div = document.createElement('div')
document.body.appendChild(div)

// 实例化组件
const vnode = createVNode(ToastComponent)
render(vnode, div)

// 向外暴露符合开发者直觉的全局快捷对象
export const toast = {
  info(msg, duration) {
    vnode.component.exposed.add(msg, 'info', duration)
  },
  success(msg, duration) {
    vnode.component.exposed.add(msg, 'success', duration)
  },
  warning(msg, duration) {
    vnode.component.exposed.add(msg, 'warning', duration)
  },
  error(msg, duration) {
    vnode.component.exposed.add(msg, 'error', duration)
  },
}
